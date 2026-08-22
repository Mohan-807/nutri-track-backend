from google import genai

from app.config import get_settings

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily built and cached (mirrors get_settings()'s own @lru_cache pattern) so importing
    this module never requires a real API key — only calling generate_reply() does."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def generate_reply(message: str) -> str:
    """The only function in the codebase that talks to Gemini directly. Deliberately the
    smallest possible shape — one string in, one string out — so chat_service.py (and everything
    upstream of it) never touches the SDK; swapping providers later means rewriting this
    function's internals only."""
    settings = get_settings()
    response = _get_client().models.generate_content(
        model=settings.gemini_model,
        contents=message,
    )
    return response.text or "Sorry, I couldn't come up with a response to that."
