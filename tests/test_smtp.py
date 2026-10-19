import socketserver
import threading
from email import policy
from email.parser import BytesParser
import pytest

from app.core.config import settings
from app.services.mail import SmtpMailAdapter


class SmtpHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 localhost test SMTP\r\n")
        while line := self.rfile.readline():
            command = line.split(b" ", 1)[0].strip().upper()
            if command == b"DATA":
                self.wfile.write(b"354 End with dot\r\n")
                message = []
                while (part := self.rfile.readline()) != b".\r\n":
                    if not part:
                        return
                    message.append(part)
                self.server.messages.append(b"".join(message))
                self.wfile.write(b"250 Accepted\r\n")
            elif command == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                return
            else:
                self.wfile.write(b"250 OK\r\n")


def test_real_loopback_smtp_adapter_uses_fragment_not_query(monkeypatch):
    server = socketserver.TCPServer(("127.0.0.1", 0), SmtpHandler)
    server.messages = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", server.server_address[1])
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(settings, "smtp_starttls", False)
    monkeypatch.setattr(settings, "smtp_username", None)
    try:
        SmtpMailAdapter().send("test@example.com", "reset", "test-token-only")
        message = BytesParser(policy=policy.default).parsebytes(server.messages[0])
        assert message["To"] == "test@example.com"
        text = message.get_content()
        assert "/reset-password#reset:test-token-only" in text
        assert "?token=" not in text and "30 menit" in text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_plain_smtp_to_remote_host_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_starttls", False)
    with pytest.raises(ValueError, match="TLS required"):
        SmtpMailAdapter().send("test@example.com", "link", "unused")
