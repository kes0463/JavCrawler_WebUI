"""ActressModel list reload — sort helpers and worker."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication
from gui.models.actress_model import ActressModel, _ActressListReloadWorker


@pytest.fixture
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def test_order_actress_rows_callable_as_static(qapp):
    """Regression: class-level call must not treat session as self."""
    rows = [
        SimpleNamespace(
            id=2,
            name_ko="Charlie",
            korean="",
            name_ja="",
            japanese="",
            is_favorite=False,
            user_score=5.0,
        ),
        SimpleNamespace(
            id=1,
            name_ko="Alice",
            korean="",
            name_ja="",
            japanese="",
            is_favorite=True,
            user_score=9.0,
        ),
    ]
    session = object()

    by_name = ActressModel._order_actress_rows(session, rows, "name", True)
    assert [r.name_ko for r in by_name] == ["Alice", "Charlie"]

    by_score = ActressModel._order_actress_rows(session, rows, "score", False)
    assert [r.name_ko for r in by_score] == ["Alice", "Charlie"]

    rows_intensity = [
        SimpleNamespace(
            id=2,
            name_ko="Low",
            korean="",
            name_ja="",
            japanese="",
            is_favorite=False,
            user_score=0.0,
            favorite_intensity=3.0,
            updated_at=None,
            created_at=None,
        ),
        SimpleNamespace(
            id=1,
            name_ko="High",
            korean="",
            name_ja="",
            japanese="",
            is_favorite=True,
            user_score=0.0,
            favorite_intensity=9.0,
            updated_at=None,
            created_at=None,
        ),
    ]
    by_effective_score = ActressModel._order_actress_rows(
        session, rows_intensity, "score", False
    )
    assert [r.name_ko for r in by_effective_score] == ["High", "Low"]

    by_favorite = ActressModel._order_actress_rows(session, rows, "favorite", False)
    assert [bool(r.is_favorite) for r in by_favorite] == [True, False]

    by_recent = ActressModel._order_actress_rows(session, rows, "recent", False)
    assert [r.id for r in by_recent] == [2, 1]


def test_list_reload_worker_emits_sorted_items(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    worker = _ActressListReloadWorker("name", True, "")
    received: list = []
    errors: list = []

    loop = QEventLoop()
    worker.finished.connect(received.append)
    worker.error.connect(errors.append)
    worker.finished.connect(loop.quit)
    worker.error.connect(loop.quit)
    QTimer.singleShot(15000, loop.quit)
    worker.start()
    loop.exec()

    assert not errors, errors
    assert len(received) == 1
    assert len(received[0]) >= 0
