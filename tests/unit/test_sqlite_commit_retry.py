"""Tests for SQLite commit retry helper."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from javstory.harvest.database import commit_with_retry


def test_commit_with_retry_succeeds_first_try():
    session = MagicMock()
    commit_with_retry(session)
    session.commit.assert_called_once()


def test_commit_with_retry_retries_on_locked(monkeypatch):
    session = MagicMock()
    session.commit.side_effect = [
        OperationalError("UPDATE", {}, Exception("database is locked")),
        None,
    ]
    sleeps: list[float] = []
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda s: sleeps.append(s))

    commit_with_retry(session, max_attempts=3, base_delay=0.01)

    assert session.commit.call_count == 2
    assert session.rollback.call_count == 1
    assert sleeps


def test_commit_with_retry_raises_after_exhausted(monkeypatch):
    session = MagicMock()
    session.commit.side_effect = OperationalError("UPDATE", {}, Exception("database is locked"))
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda _s: None)

    with pytest.raises(OperationalError):
        commit_with_retry(session, max_attempts=2, base_delay=0.01)

    assert session.commit.call_count == 2
