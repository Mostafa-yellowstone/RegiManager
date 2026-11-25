"""Read a login OTP from the carrier's OTP mailbox.

Flow for an adapter: note `requested_at` right before it asks the portal to send a code, then call
`fetch_otp(mailbox, sender_hints, requested_at)`. Only mail that (a) arrived after requested_at and
(b) comes from an expected sender domain is considered. The newest match wins. The code is returned
to the caller and never logged or stored.
"""
from __future__ import annotations

import email
import imaplib
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Callable, Protocol


@dataclass
class MailItem:
    sender: str
    subject: str
    body: str
    received_at: datetime  # timezone-aware


class Mailbox(Protocol):
    def recent(self, since: datetime) -> list[MailItem]: ...


class OtpNotFound(Exception):
    pass


_KEYWORDS = r"(?:code|otp|passcode|pin|verification|verify|security)"
_PATTERNS = [
    re.compile(rf"{_KEYWORDS}[^0-9]{{0,40}}(\d{{6}})(?!\d)", re.I),
    re.compile(rf"(?<!\d)(\d{{6}})(?!\d)[^0-9]{{0,40}}{_KEYWORDS}", re.I),
    re.compile(rf"{_KEYWORDS}[^0-9]{{0,40}}(\d{{4,8}})(?!\d)", re.I),
    re.compile(r"(?<![\d$.,-])(\d{6})(?![\d.,%])"),
]


def extract_code(text: str) -> str | None:
    """Pull the one-time code out of an email body. Keyword-anchored first, bare 6 digits last."""
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t)
    for pat in _PATTERNS:
        m = pat.search(t)
        if m:
            return m.group(1)
    return None


def _sender_ok(sender: str, hints: list[str]) -> bool:
    s = sender.lower()
    return not hints or any(h.lower().lstrip("@") in s for h in hints)


def fetch_otp(mailbox: Mailbox, sender_hints: list[str], requested_at: datetime, timeout_s: float = 90,
              poll_s: float = 4, sleep: Callable[[float], None] = time.sleep,
              now: Callable[[], float] = time.monotonic) -> str:
    """Poll the mailbox until a fresh OTP arrives. Raises OtpNotFound on timeout (caller asks a human)."""
    if requested_at.tzinfo is None:
        raise ValueError("requested_at must be timezone-aware")
    since = requested_at - timedelta(seconds=5)  # small clock skew allowance
    deadline = now() + timeout_s
    while True:
        items = [m for m in mailbox.recent(since) if m.received_at >= since and _sender_ok(m.sender, sender_hints)]
        for m in sorted(items, key=lambda x: x.received_at, reverse=True):
            code = extract_code(f"{m.subject} {m.body}")
            if code:
                return code
        if now() >= deadline:
            raise OtpNotFound("No OTP email arrived in time from the expected sender.")
        sleep(poll_s)


class ImapMailbox:
    """Read-only IMAP access (use an app password for the OTP mailbox). Never deletes or flags mail."""

    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX", port: int = 993):
        self.host, self.user, self.password, self.folder, self.port = host, user, password, folder, port

    def recent(self, since: datetime) -> list[MailItem]:
        out: list[MailItem] = []
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            conn.login(self.user, self.password)
            conn.select(self.folder, readonly=True)
            day = since.astimezone(timezone.utc).strftime("%d-%b-%Y")
            typ, data = conn.search(None, "SINCE", day)
            ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-30:]
            for i in ids:
                typ, msg_data = conn.fetch(i, "(BODY.PEEK[])")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                try:
                    when = parsedate_to_datetime(msg.get("Date"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                out.append(MailItem(sender=str(msg.get("From", "")), subject=str(msg.get("Subject", "")),
                                    body=_body_text(msg), received_at=when))
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return out


def _body_text(msg: Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    chunks = []
    for p in parts:
        if p.get_content_type() in ("text/plain", "text/html"):
            payload = p.get_payload(decode=True) or b""
            chunks.append(payload.decode(p.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(chunks)
