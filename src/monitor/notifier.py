"""Alert notifier: email (smtplib) and WeChat Work webhook."""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(
        self,
        smtp_host: str,
        port: int,
        sender: str,
        receiver: str,
        password: str,
    ) -> None:
        self._smtp_host = smtp_host
        self._port = port
        self._sender = sender
        self._receiver = receiver
        self._password = password

    def send(self, subject: str, body: str) -> bool:
        if not self._sender or not self._receiver:
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self._sender
            msg["To"] = self._receiver
            msg.set_content(body)
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self._smtp_host, self._port, context=ctx) as s:
                s.login(self._sender, self._password)
                s.send_message(msg)
            logger.info(f"Email sent: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email failed: {e}")
            return False


class WeChatNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def send(self, content: str) -> bool:
        if not self._url:
            return False
        try:
            import urllib.request
            payload = json.dumps({"msgtype": "text", "text": {"content": content}}).encode()
            req = urllib.request.Request(
                self._url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                ok = json.loads(resp.read()).get("errcode", -1) == 0
            if ok:
                logger.info(f"WeChat notification sent: {content[:40]}")
            return ok
        except Exception as e:
            logger.error(f"WeChat notification failed: {e}")
            return False


class Notifier:
    """Fanout notifier: sends to all configured channels."""

    def __init__(
        self,
        email: Optional[EmailNotifier] = None,
        wechat: Optional[WeChatNotifier] = None,
    ) -> None:
        self._channels = [c for c in [email, wechat] if c is not None]

    def alert(self, subject: str, body: str) -> None:
        for ch in self._channels:
            ch.send(subject, body)

    @classmethod
    def from_settings(cls, email_password: str = "") -> "Notifier":
        from src.utils.config import get_settings
        cfg = get_settings().notifier
        email = None
        if cfg.email.sender and email_password:
            email = EmailNotifier(
                cfg.email.smtp_host, cfg.email.port,
                cfg.email.sender, cfg.email.receiver, email_password,
            )
        wechat = WeChatNotifier(cfg.wechat_webhook) if cfg.wechat_webhook else None
        return cls(email=email, wechat=wechat)
