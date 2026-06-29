"""Harvest product code validation."""

from __future__ import annotations

from javstory.utils.product_code import is_plausible_harvest_code


def test_rejects_single_letter():
    assert is_plausible_harvest_code("B") is False


def test_accepts_normal_code():
    assert is_plausible_harvest_code("STARS-001") is True
    assert is_plausible_harvest_code("IPX-123") is True
