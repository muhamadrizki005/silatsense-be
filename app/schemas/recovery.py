from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
from app.schemas.auth import SignIn


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecoveryAccepted(StrictInput):
    detail: str = "Jika memenuhi syarat, instruksi akan dikirim."


class Reauthenticate(StrictInput):
    currentPassword: str = Field(min_length=8, max_length=128)


class EmailLinkRequest(Reauthenticate):
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize(cls, value):
        return str(value).lower()


class TokenConfirm(StrictInput):
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ResetRequest(StrictInput):
    identifier: str = Field(max_length=254)
    normalize_identifier = field_validator("identifier")(
        SignIn.normalize_identifier.__func__
    )


class ResetConfirm(TokenConfirm):
    newPassword: str = Field(min_length=8, max_length=128)
