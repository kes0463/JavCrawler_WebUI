"""OpenRouter 크레딧 부족 감지."""

from __future__ import annotations

import pytest

from javstory.translation.llm_backoff import is_openrouter_credit_exhausted


class _Fake402(Exception):
    status_code = 402


def test_openrouter_credit_exhausted_by_status_code() -> None:
    assert is_openrouter_credit_exhausted(_Fake402("payment required"))


@pytest.mark.parametrize(
    "msg",
    [
        "Error 402: insufficient credits",
        "HTTP 402 Payment Required: Your account has insufficient credits",
        "This request requires more credits, or fewer max_tokens. You requested up to 64000 tokens, but can only afford 17176.",
    ],
)
def test_openrouter_credit_exhausted_by_message(msg: str) -> None:
    assert is_openrouter_credit_exhausted(msg)


def test_openrouter_credit_not_matched_for_rate_limit() -> None:
    assert not is_openrouter_credit_exhausted("429 Too Many Requests: rate limit exceeded")
