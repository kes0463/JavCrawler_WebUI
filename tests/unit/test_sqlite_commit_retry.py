"""Tests for SQLite write-retry helpers (commit_with_retry / run_write_txn)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, PendingRollbackError

from javstory.harvest.database import commit_with_retry, run_write_txn


def _locked(sql: str = "UPDATE") -> OperationalError:
    return OperationalError(sql, {}, Exception("database is locked"))


def test_commit_with_retry_succeeds_first_try():
    session = MagicMock()
    commit_with_retry(session)
    session.commit.assert_called_once()


def test_commit_with_retry_retries_on_locked(monkeypatch):
    session = MagicMock()
    session.commit.side_effect = [_locked(), None]
    sleeps: list[float] = []
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda s: sleeps.append(s))

    commit_with_retry(session, max_attempts=3, base_delay=0.01)

    assert session.commit.call_count == 2
    assert session.rollback.call_count == 1
    assert sleeps


def test_commit_with_retry_raises_after_exhausted(monkeypatch):
    session = MagicMock()
    session.commit.side_effect = _locked()
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda _s: None)

    with pytest.raises(OperationalError):
        commit_with_retry(session, max_attempts=2, base_delay=0.01)

    assert session.commit.call_count == 2


def test_commit_with_retry_handles_pending_rollback(monkeypatch):
    # flush 중 락 → rollback 없이 재사용 시 나오는 PendingRollbackError 도 락으로 취급.
    session = MagicMock()
    pending = PendingRollbackError(
        "This Session's transaction has been rolled back ... "
        "Original exception was: (sqlite3.OperationalError) database is locked"
    )
    session.commit.side_effect = [pending, None]
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda _s: None)

    commit_with_retry(session, max_attempts=3, base_delay=0.01)

    assert session.commit.call_count == 2
    assert session.rollback.call_count == 1


def test_run_write_txn_reruns_unit_of_work_on_lock(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def work():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _locked("INSERT INTO jav_metadata")
        return "ok"

    assert run_write_txn(session, work, max_attempts=4, base_delay=0.01) == "ok"
    assert calls["n"] == 2
    # 재시도 전에 트랜잭션 전체를 되돌린다.
    assert session.rollback.call_count == 1


def test_run_write_txn_reraises_non_lock(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda _s: None)

    def work():
        raise OperationalError("INSERT", {}, Exception("no such table: foo"))

    with pytest.raises(OperationalError):
        run_write_txn(session, work, max_attempts=3, base_delay=0.01)
    session.rollback.assert_not_called()


def test_run_write_txn_exhausts(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr("javstory.harvest.database.time.sleep", lambda _s: None)

    def work():
        raise _locked()

    with pytest.raises(OperationalError):
        run_write_txn(session, work, max_attempts=3, base_delay=0.01)
    assert session.rollback.call_count == 3
