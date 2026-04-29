"""파이프라인 단계 스킵 판단용 상태(파일·DB 목)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from javstory.pipeline.orchestrator import ProductPipelineStatus, get_pipeline_status


def test_get_pipeline_status_no_video() -> None:
    with patch("javstory.harvest.database.get_db_session") as g:
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = None
        g.return_value = sess
        st = get_pipeline_status(product_code="TST-001", video_path=None)
        assert st.product_code == "TST-001"
        assert st.video_path is None
        assert st.ja_srt_path is None
        assert st.harvest_in_db is False


def test_get_pipeline_status_harvest_true(tmp_path) -> None:
    with patch("javstory.harvest.database.get_db_session") as g:
        sess = MagicMock()
        row = MagicMock()
        row.title_ko = "제목"
        row.title_ja = ""
        row.original_title = ""
        sess.query.return_value.filter_by.return_value.first.return_value = row
        g.return_value = sess
        st = get_pipeline_status(product_code="abc-999", video_path=None)
        assert st.harvest_in_db is True


def test_product_pipeline_status_fields() -> None:
    st = ProductPipelineStatus(
        product_code="X",
        video_path=None,
        harvest_in_db=False,
        ja_srt_path=None,
        ja_srt_exists=False,
        ko_srt_path=None,
        ko_srt_exists=False,
    )
    assert st.product_code == "X"
