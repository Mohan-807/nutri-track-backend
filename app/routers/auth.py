from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.models.user import User
from app.schemas.auth import AuthOut, LoginIn, SignupIn, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/signup", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def signup(data: SignupIn, db: DbSession) -> AuthOut:
    email = _normalize_email(data.email)
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")

    user = User(email=email, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return AuthOut(user=UserOut.model_validate(user), token=token)


@router.post("/login", response_model=AuthOut)
def login(data: LoginIn, db: DbSession) -> AuthOut:
    email = _normalize_email(data.email)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    token = create_access_token(user.id)
    return AuthOut(user=UserOut.model_validate(user), token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
