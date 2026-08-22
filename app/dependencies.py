from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.security import decode_access_token

# HTTPBearer (not OAuth2PasswordBearer) — login/signup take a JSON body, not an OAuth2
# form-encoded request, so there's no "token URL" flow to model here.
bearer_scheme = HTTPBearer()

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise unauthorized from exc

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


# Shared type aliases so routers write `db: DbSession` / `current_user: CurrentUser` instead of
# repeating `= Depends(...)` in every handler's default arguments.
CurrentUser = Annotated[User, Depends(get_current_user)]
