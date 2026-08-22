from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import CamelModel


class SignupIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginIn(CamelModel):
    email: EmailStr
    password: str


class UserOut(CamelModel):
    id: int
    email: str
    created_at: datetime


class AuthOut(CamelModel):
    user: UserOut
    token: str
