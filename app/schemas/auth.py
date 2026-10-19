import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, field_validator
from typing import Literal


class SignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    rememberMe: bool = False

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value):
        value = value.strip()
        if re.fullmatch(r"[0-9]{8,12}", value):
            return value
        return str(TypeAdapter(EmailStr).validate_python(value)).lower()


class SignUp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fullName: str = Field(min_length=3, max_length=120)
    identifier: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    normalize_identifier = field_validator("identifier")(SignIn.normalize_identifier.__func__)

    @field_validator("fullName")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Nama minimal 3 karakter")
        return value


class AuthUser(BaseModel):
    id: str
    fullName: str
    identifier: str
    role: Literal["member", "coach"]


class AuthTokens(BaseModel):
    user: AuthUser
    accessToken: str
    expiresIn: int
