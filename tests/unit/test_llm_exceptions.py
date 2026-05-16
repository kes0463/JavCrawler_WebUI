"""LLM 라우터 예외 타입."""

from __future__ import annotations

import pytest

from javstory.llm.engine import AllTiersExhaustedError, JSONValidationError


def test_all_tiers_exhausted_error_attributes() -> None:
    err = AllTiersExhaustedError(
        "모든 AI 티어가 응답에 실패했거나 검열되었습니다.",
        last_model="DeepSeek V3",
        last_error="HTTPError",
    )
    assert str(err) == "모든 AI 티어가 응답에 실패했거나 검열되었습니다."
    assert err.last_model == "DeepSeek V3"
    assert err.last_error == "HTTPError"
    with pytest.raises(AllTiersExhaustedError):
        raise err


def test_all_tiers_exhausted_error_optional_fields_default_none() -> None:
    err = AllTiersExhaustedError("failed")
    assert err.last_model is None
    assert err.last_error is None


def test_json_validation_error_is_distinct() -> None:
    assert not issubclass(JSONValidationError, AllTiersExhaustedError)
