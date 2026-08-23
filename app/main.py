import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, chat, foods, logs, profile

settings = get_settings()

# Uvicorn only configures its own loggers, leaving the root logger at WARNING — so without this,
# every logger.info() in the app is silently dropped, including LLM token-usage/cost tracking and
# provider-failover decisions. Attached to the "app" logger only, so third-party libraries stay at
# their own (noisier) defaults.
logging.basicConfig(format="%(levelname)s:     %(name)s - %(message)s")
logging.getLogger("app").setLevel(logging.DEBUG if settings.environment == "development" else logging.INFO)

app = FastAPI(title="Nutri Tracker API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(foods.router)
app.include_router(logs.router)
app.include_router(chat.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
