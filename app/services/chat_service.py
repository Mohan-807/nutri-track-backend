import logging
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime
from datetime import time as time_of_day

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.user import User
from app.services.chat_prompts import SYSTEM_INSTRUCTION
from app.services.llm_service import LlmError, stream_turn
from app.services.tools import TOOL_DECLARATIONS, get_tool

logger = logging.getLogger(__name__)

# --- Security boundaries (Step 8) ---------------------------------------------------------
# The LLM is a request generator, never an authority. Concretely:
#   1. Authentication: send_message_stream()/get_history() only ever run behind the /chat
#      router's CurrentUser dependency (JWT) — there is no path to either that skips it.
#   2. Authorization: every tool scopes its DB queries to the `current_user` object passed in
#      here, which came from the authenticated request — never from a user id the model supplies
#      in its arguments. Cross-user access is structurally impossible, not just checked for.
#   3. Tool allowlisting: TOOL_REGISTRY (app/services/tools/__init__.py) is the only source of
#      what's callable; an unrecognized name is rejected in _run_tool() below.
#   4. Argument validation: each tool validates its own args via a pydantic model before doing
#      anything else (e.g. LogFoodEntryArgs, AddFoodToCatalogArgs) — malformed/out-of-range
#      input never reaches a service function.
#   5. Business-rule validation: AI-*estimated* data gets tighter bounds than human-entered data
#      (see add_food_to_catalog.py's calorie/macro ceilings, log_food_entry.py's quantity
#      ceiling) and is tagged category="ai_estimated" rather than blended in as if verified.
#   6. Bounded execution: MAX_TOOL_ROUNDS below caps how many tool calls one request can trigger,
#      independent of what the model "wants" to keep doing.
# What's deliberately NOT here: interactive confirmation before a tool runs. This app's tool
# actions (log an entry, add a catalog row) are low-stakes and correctable via the existing UI
# (delete/edit), unlike, say, an irreversible payment — "confirmation when appropriate" (per the
# roadmap) means it isn't appropriate here, not that it was overlooked.
# --------------------------------------------------------------------------------------------

# Bounds both LLM cost/latency and context-window usage — every message here is re-sent to
# Gemini on every turn (the API is stateless; it has no memory of past requests). 20 messages is
# roughly the last 10 back-and-forth turns, oldest dropped first. A production app with much
# longer-running conversations would eventually want summarization instead of a hard window;
# out of scope for this app's chat length.
HISTORY_LIMIT_FOR_LLM = 20

# A hard ceiling on tool round-trips within a single user message, independent of anything the
# model "decides" — without this, a model stuck calling tools back-to-back (a bad tool result it
# keeps retrying, a confused loop) could hammer the LLM API and the database indefinitely on one
# request. This is a backend-enforced limit; the LLM has no say in it.
MAX_TOOL_ROUNDS = 5

# Persisted rows already use the neutral vocabulary ("user"/"assistant"), so replaying history
# needs no role mapping — each provider translates to its own wire format (see
# llm_providers/base.py for the neutral turn shape).

# Rate limiting (Step 11) — a real constraint discovered live while building this: the free-tier
# Gemini key this app uses is capped at a small number of requests *per day*, and one user
# message can burn several of them (one per tool round-trip). A minimum gap between messages
# from the same user is a simple, cheap guard against accidental rapid-fire sends (double
# submits, holding Enter) chewing through that budget for no benefit. In-memory and per-process
# — correct for this app's actual deployment (a single backend instance); a multi-instance
# production deployment would need a shared store (e.g. Redis) instead, since each process would
# otherwise track its own separate cooldown.
MIN_SECONDS_BETWEEN_MESSAGES = 3.0
_last_message_at: dict[int, float] = {}


def _check_rate_limit(user_id: int) -> str | None:
    now = time.monotonic()
    last = _last_message_at.get(user_id)
    if last is not None and (now - last) < MIN_SECONDS_BETWEEN_MESSAGES:
        wait = MIN_SECONDS_BETWEEN_MESSAGES - (now - last)
        return f"You're sending messages too quickly — please wait {wait:.0f}s and try again."
    _last_message_at[user_id] = now
    return None


def _reset_rate_limit_state_for_tests() -> None:
    """Test-only hook. Tests each get a fresh in-memory database, so numeric user ids (1, 2, ...)
    are reused across otherwise-unrelated tests — without clearing this between them, one test's
    timing could spuriously rate-limit a completely different later test."""
    _last_message_at.clear()


# Chat history is deliberately short-lived — only the current calendar day's conversation is
# kept. Unlike everything else in this app (log entries, foods), a chat transcript has no lasting
# value here once the day it happened is over, and letting it grow forever would also keep
# inflating HISTORY_LIMIT_FOR_LLM's window with stale, irrelevant turns. Scoped ONLY to
# chat_messages — log history, food catalog, etc. are untouched and keep their full history.
def _start_of_today_utc() -> datetime:
    return datetime.combine(datetime.now(UTC).date(), time_of_day.min, tzinfo=UTC)


def _clear_previous_days(db: Session, user_id: int) -> None:
    cutoff = _start_of_today_utc()
    # synchronize_session="fetch" (not the cheaper False): this deletes rows that may already be
    # tracked in the session's identity map (e.g. loaded earlier in the same request/test) —
    # skipping sync there leaves stale Python objects referencing now-deleted rows, which then
    # collide with a *new* row that reuses the same id (observed as a real SAWarning in tests).
    deleted = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.created_at < cutoff)
        .delete(synchronize_session="fetch")
    )
    if deleted:
        db.commit()
        logger.info("Cleared %d chat message(s) from a previous day for user %s", deleted, user_id)


def _load_recent_messages(db: Session, user_id: int, limit: int) -> list[ChatMessage]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))  # newest-first from the query, back to chronological order


def _build_turns(messages: list[ChatMessage]) -> list[dict]:
    return [{"role": m.role, "text": m.content} for m in messages]


def _run_tool(db: Session, current_user: User, name: str, args: dict, today: date) -> dict:
    """The backend is the authority here, never the LLM: an unrecognized name is rejected by the
    registry itself (get_tool returning None — the allowlist), a tool's own pydantic model
    rejects bad/missing arguments, and any other failure is caught rather than crashing the
    whole request. Every case returns a plain result dict the model sees as a normal tool
    outcome — it can react to "invalid arguments" or "failed" the same way it reacts to any
    other tool result, instead of the request dying."""
    tool = get_tool(name)
    if tool is None:
        logger.warning("LLM requested unknown tool '%s'", name)
        return {"error": f"Unknown tool '{name}'."}

    try:
        return tool.execute(db, current_user, args, today)
    except ValidationError as exc:
        db.rollback()
        first_error = exc.errors()[0]["msg"] if exc.errors() else str(exc)
        return {"error": f"Invalid arguments for {name}: {first_error}"}
    except Exception:
        # Covers a tool's own DB write failing (constraint violation, connection blip, etc.) —
        # rollback is required here, not optional: a failed commit leaves the SQLAlchemy session
        # in a state that raises on every further query until rolled back, which would silently
        # break every remaining tool call and the final assistant-message commit in this request.
        db.rollback()
        logger.exception("Tool '%s' failed", name)
        return {"error": f"{name} failed unexpectedly."}


def send_message_stream(db: Session, user_id: int, message: str, client_date: date | None = None) -> Iterator[dict]:
    """Persist the user's turn, then run the LLM in a loop that may call tools before producing
    a final reply — yielding plain-dict events the /chat router turns into SSE:
      {"type": "provider", "provider", "model"}  — which AI is serving this request
      {"type": "chunk", "text"}            — a piece of the final answer's text
      {"type": "tool_call", "name", "args"}
      {"type": "tool_result", "name", "success"}
      {"type": "done", "reply", "provider", "model"}  — always the last event on success
      {"type": "error", "message"}         — replaces "done" if something failed
    Only the user's message and the model's final text are persisted to ChatMessage —
    intermediate tool calls/results are ephemeral, rebuilt fresh each request, not stored as
    their own rows. The provider/model that produced the reply IS persisted on that row.

    Every failure mode below — LLM API failure, rate limit, timeout, streaming interruption
    (a connection drop after some chunks already arrived), or a database error persisting a
    message — degrades to one clean {"type": "error"} event instead of an unhandled exception
    killing the connection outright. Nothing here is automatically retried: a rate limit
    retrying instantly just fails again and burns more of a scarce quota; a validation or
    business-logic failure retrying wouldn't change the outcome. The one thing genuinely worth
    auto-retrying — a transient network blip — is surfaced as `retryable` on LlmError for a
    future caller to act on, not retried blindly here."""
    rate_limit_message = _check_rate_limit(user_id)
    if rate_limit_message is not None:
        yield {"type": "error", "message": rate_limit_message}
        return

    # The user's local calendar date, threaded explicitly into every tool call below (see
    # ToolSpec in tools/base.py) rather than stashed in thread-local/request-scoped state: a
    # streamed response's generator can genuinely resume on a different threadpool worker thread
    # between yields, so a value set once at the top would not reliably still be visible several
    # tool calls later in the same request.
    today = client_date or datetime.now(UTC).date()

    try:
        current_user = db.get(User, user_id)

        _clear_previous_days(db, user_id)

        user_turn = ChatMessage(user_id=user_id, role="user", content=message)
        db.add(user_turn)
        db.commit()

        recent = _load_recent_messages(db, user_id, HISTORY_LIMIT_FOR_LLM)
        turns = _build_turns(recent)

        reply = None
        provider = None
        model = None
        for _ in range(MAX_TOOL_ROUNDS):
            function_call = None
            for event in stream_turn(turns, system_instruction=SYSTEM_INSTRUCTION, tools=TOOL_DECLARATIONS):
                if event["type"] == "provider":
                    # Tracked per round: a failover between tool rounds means a later round can be
                    # served by a different model than the first, and the row should record whoever
                    # produced the final answer.
                    provider, model = event["provider"], event["model"]
                    yield event
                elif event["type"] == "chunk":
                    yield {"type": "chunk", "text": event["text"]}
                elif event["type"] == "function_call":
                    function_call = event
                elif event["type"] == "done":
                    reply = event["text"]

            if function_call is None:
                break  # the round ended in a final text reply — stop looping

            # Recorded as a neutral turn (not a provider SDK object) so a failover on the *next*
            # round can replay this same tool exchange to a different provider.
            turns.append({"role": "assistant", "tool_call": {k: function_call[k] for k in ("id", "name", "args")}})
            yield {"type": "tool_call", "name": function_call["name"], "args": function_call["args"]}

            result = _run_tool(db, current_user, function_call["name"], function_call["args"], today)
            yield {"type": "tool_result", "name": function_call["name"], "success": "error" not in result}
            turns.append(
                {
                    "role": "tool",
                    "tool_call_id": function_call["id"],
                    "name": function_call["name"],
                    "result": result,
                }
            )

        if reply is None:
            reply = "Sorry, that took too many steps to finish — please try rephrasing your request."

        assistant_turn = ChatMessage(
            user_id=user_id, role="assistant", content=reply, provider=provider, model=model
        )
        db.add(assistant_turn)
        db.commit()
    except LlmError as exc:
        # Expected, classified failure from llm_service (rate limit, upstream outage, network) —
        # exc.message is already a clean, accurate, user-facing string; log at warning, not
        # exception, since there's no bug here to investigate.
        db.rollback()
        logger.warning("LLM call failed for user %s: %s", user_id, exc.message)
        yield {"type": "error", "message": exc.message}
        return
    except Exception:
        # Anything else — a DB error persisting a message, a bug — is unexpected; log the full
        # traceback, but the user still gets a clean message, never a raw stack trace.
        db.rollback()
        logger.exception("Chat request failed for user %s", user_id)
        yield {"type": "error", "message": "Sorry, something went wrong. Please try again."}
        return

    yield {"type": "done", "reply": reply, "provider": provider, "model": model}


def get_history(db: Session, user_id: int, limit: int = 200) -> list[ChatMessage]:
    """The transcript the frontend loads on mount — a much higher cap than
    HISTORY_LIMIT_FOR_LLM, which only bounds what's sent *to the LLM* per turn, not what the UI
    is allowed to show. Also clears any previous day's leftovers (see _clear_previous_days) so
    opening the chat tab on a new day shows a clean slate immediately, without waiting for the
    user to send a first message."""
    _clear_previous_days(db, user_id)
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at)
        .limit(limit)
        .all()
    )
