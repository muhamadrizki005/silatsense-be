"""No token logging or disk spool. Test adapter is injected, never selectable by env."""

from dataclasses import dataclass, field
from email.message import EmailMessage
import ipaddress
import smtplib
import ssl
from typing import Protocol

from app.core.config import settings
from app.core.errors import DomainError


class MailAdapter(Protocol):
    def send(self, recipient: str, purpose: str, token: str) -> None: ...


@dataclass
class MemoryMailAdapter:
    messages: list[dict] = field(default_factory=list, repr=False)

    def send(self, recipient, purpose, token):
        self.messages.append(dict(recipient=recipient, purpose=purpose, token=token))


class SmtpMailAdapter:
    def send(self, recipient, purpose, token):
        # Plain SMTP is allowed only for an explicitly configured loopback test server.
        try:
            loopback = (
                settings.smtp_host == "localhost"
                or ipaddress.ip_address(settings.smtp_host).is_loopback
            )
        except ValueError:
            loopback = False
        if not settings.smtp_starttls and not loopback:
            raise ValueError("SMTP TLS required")
        message = EmailMessage()
        message["Subject"] = "SilatSense — konfirmasi keamanan akun"
        message["From"] = settings.smtp_from
        message["To"] = recipient
        route = "/reset-password" if purpose == "reset" else "/confirm-email"
        # Fragment is never sent to the HTTP server or its access logs.
        message.set_content(
            f"Buka {settings.frontend_origin}{route}#{purpose}:{token}\n"
            "Jangan bagikan tautan ini. Abaikan jika Anda tidak meminta perubahan.\n"
            + ("Berlaku 30 menit." if purpose == "reset" else "Berlaku 24 jam.")
        )
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)


def get_mail_adapter() -> MailAdapter:
    if settings.mail_adapter != "smtp":
        raise DomainError(503, "mail_unavailable", "Layanan email belum tersedia.")
    return SmtpMailAdapter()
