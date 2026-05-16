"""품번 추출·resolve_product_code_for_video."""

from __future__ import annotations

from javstory.utils.product_code import (
    extract_product_code_from_path,
    resolve_product_code_for_video,
)


def test_extract_product_code_from_path_standard() -> None:
    pc = extract_product_code_from_path(r"D:\media\ABW-358\ABW-358_part2.mp4")
    assert pc == "ABW-358"


def test_extract_product_code_strips_part_suffix() -> None:
    pc = extract_product_code_from_path("E:/x/SAME-001_Part_2.mkv")
    assert pc == "SAME-001"


def test_resolve_product_code_prefers_path_over_hint() -> None:
    pc = resolve_product_code_for_video(
        r"D:\works\ABW-358\ABW-358_cd1.mp4",
        "WRONG-000",
    )
    assert pc == "ABW-358"


def test_resolve_product_code_uses_hint_when_path_has_no_code() -> None:
    pc = resolve_product_code_for_video("D:/misc/intro_clip.mp4", "hint-777")
    assert pc == "HINT-777"


def test_resolve_product_code_stem_fallback() -> None:
    pc = resolve_product_code_for_video("folder/no_code_name.mp4", None)
    assert pc == "NO_CODE_NAME"
