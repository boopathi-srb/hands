"""Cookie-backed teller sessions and credential checks."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

SESSION_COOKIE_NAME = "CORESESSID"


@dataclass(frozen=True)
class TellerSession:
    token: str
    user_id: str
    tenant: str


class SessionStore:
    """In-memory session table keyed by an opaque random token."""

    def __init__(self) -> None:
        self._sessions: dict[str, TellerSession] = {}

    def create(self, user_id: str, tenant: str) -> TellerSession:
        session = TellerSession(token=secrets.token_urlsafe(24), user_id=user_id, tenant=tenant)
        self._sessions[session.token] = session
        return session

    def get(self, token: str | None, tenant: str) -> TellerSession | None:
        """Return the session for a token only if it exists and belongs to this tenant."""
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None or session.tenant != tenant:
            return None
        return session

    def revoke(self, token: str | None) -> bool:
        """Remove a session. Returns True when one existed."""
        if not token:
            return False
        return self._sessions.pop(token, None) is not None


def credentials_match(
    submitted_user_id: str, submitted_password: str, user_id: str, password: str
) -> bool:
    """Constant-time comparison of submitted credentials against the configured teller."""
    user_matches = secrets.compare_digest(submitted_user_id.encode(), user_id.encode())
    password_matches = secrets.compare_digest(submitted_password.encode(), password.encode())
    return user_matches and password_matches


def answer_matches(submitted_answer: str, expected_answer: str) -> bool:
    """Constant-time comparison for the identity-check supervisor override."""
    return secrets.compare_digest(submitted_answer.encode(), expected_answer.encode())
