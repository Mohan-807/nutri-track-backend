import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.main import app
from app.models.food import Food
from app.services.chat_service import _reset_rate_limit_state_for_tests

# Tests never run Alembic and never touch Postgres — schema comes from Base.metadata.create_all()
# against a throwaway in-memory SQLite DB, always in sync with the current model code. The real
# dev/prod database is provisioned exclusively via `alembic upgrade head` against Postgres.


@pytest.fixture(autouse=True)
def _reset_chat_rate_limit():
    # chat_service's rate limiter is in-memory and keyed by user id; each test gets a fresh
    # database where ids restart at 1, so without this, one test's timing could spuriously
    # rate-limit an unrelated later test reusing the same id.
    _reset_rate_limit_state_for_tests()
    yield


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # keeps the single in-memory connection alive across the test
    )
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def signup_and_login(client, email="test@example.com", password="pw123456"):
    client.post("/auth/signup", json={"email": email, "password": password})
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response.json()


@pytest.fixture()
def auth_headers(client):
    auth = signup_and_login(client)
    return {"Authorization": f"Bearer {auth['token']}"}


@pytest.fixture()
def sample_food(db_session):
    food = Food(
        name="Test Apple",
        aliases=["apples"],
        category="fruit",
        serving_label="1 medium (182g)",
        serving_grams=182,
        calories=95,
        protein_g=0.5,
        carbs_g=25,
        fat_g=0.3,
        fiber_g=4.4,
        sugar_g=19,
        sodium_mg=2,
    )
    db_session.add(food)
    db_session.commit()
    db_session.refresh(food)
    return food
