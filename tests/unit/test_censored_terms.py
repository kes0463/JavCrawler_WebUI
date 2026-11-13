"""Allowlisted storefront mask restoration for harvest metadata translation."""

from __future__ import annotations

import json

import pytest

from javstory.harvest.censored_terms import (
    accept_mask_restore,
    apply_restore_response,
    build_mask_restore_messages,
    collect_restore_windows,
    restore_censored_text,
)
from javstory.harvest.translator import (
    build_metadata_translation_messages,
    fill_unresolved_masks,
)


def test_user_allowlist_compounds():
    cases = {
        "奴●契約": ("奴隷契約", [("奴隷契約", "노예 계약")]),
        "アナル＆マ●コ": ("アナル＆マンコ", [("マンコ", "보지")]),
        "レ×プ輪●": ("レイプ輪姦", [("レイプ", "강간"), ("輪姦", "윤간")]),
        "チ●ポ": ("チンポ", [("チンポ", "자지")]),
        "チ○ポ": ("チンポ", [("チンポ", "자지")]),
        "ち●ぽ": ("ちんぽ", [("ちんぽ", "자지")]),
        "家庭●師": ("家庭教師", [("家庭教師", "가정교사")]),
        "輪●されて": ("輪姦されて", [("輪姦", "윤간")]),
        "強●される": ("強姦される", [("強姦される", "강간당하다")]),
        "痴●レ×プ": ("痴漢レイプ", [("痴漢", "치한"), ("レイプ", "강간")]),
        "夜●い": ("夜這い", [("夜這い", "야바이")]),
        "犯●れて": ("犯されて", [("犯されて", "범해져서")]),
        "犯●れた夏": ("犯された夏", [("犯された", "범해진")]),
        "犯●れまくった": ("犯されまくった", [("犯され", "범해져")]),
        "おま●こ": ("おまんこ", [("おまんこ", "보지")]),
        "おま○こ": ("おまんこ", [("おまんこ", "보지")]),
        "オマ●コびっしょびしょ": ("オマンコびっしょびしょ", [("オマンコ", "보지")]),
        "ま●こ": ("まんこ", [("まんこ", "보지")]),
        "口マ●コ": ("口マンコ", [("口マンコ", "입보지")]),
        "奴●調教": ("奴隷調教", [("奴隷", "노예")]),
        "チ○ポ奴●": ("チンポ奴隷", [("チンポ", "자지"), ("奴隷", "노예")]),
        "逆レ●プ勧奨": ("逆レイプ勧奨", [("逆レイプ", "역강간")]),
        "昏●5P": ("昏睡5P", [("昏睡", "혼수")]),
        "凌●調教": ("凌辱調教", [("凌辱", "능욕")]),
        "敏感媚●": ("敏感媚薬", [("媚薬", "미약")]),
        "強●射精": ("強制射精", [("強制射精", "강제 사정")]),
        "強●勃起": ("強制勃起", [("強制勃起", "강제 발기")]),
        "強●レ×プ": ("強姦レイプ", [("強姦レイプ", "강간")]),
    }
    for src, (expected, terms) in cases.items():
        got = restore_censored_text(src)
        assert got.text == expected, src
        assert got.terms == tuple(terms), src


def test_bare_strong_mask_stays_for_the_restore_call():
    got = restore_censored_text("強●受胎闇市場")
    assert got.text == "強●受胎闇市場"
    assert got.terms == ()
    windows = collect_restore_windows(got.text, "")
    assert len(windows) == 1
    assert "強●" in windows[0].snippet


def test_forced_shame_is_not_rape():
    got = restore_censored_text("強●羞恥エクスタシー")
    assert got.text == "強制羞恥エクスタシー"
    assert got.terms == (("強制羞恥", "강제 수치"),)


def test_unknown_masks_stay_unchanged_and_are_not_sent():
    samples = (
        "激カワ小悪魔J●達",
        "不良ギャルJ×の固定",
        "甥っ子シ●タをいただく",
        "小悪魔女子●生",
        "美少女ロ●",
        "夜市",
        "痴女られる",
    )
    for src in samples:
        got = restore_censored_text(src)
        assert got.text == src
        assert got.terms == ()
        assert collect_restore_windows(got.text, "") == ()


def test_lotion_mask_can_still_be_sent():
    windows = collect_restore_windows("ロ●ションを塗る", "")
    assert len(windows) == 1
    assert "ロ●ション" in windows[0].snippet


def test_excluded_span_is_cut_out_of_the_restore_window():
    text = "女子●生とド●ペリ"
    windows = collect_restore_windows(text, "")
    assert len(windows) == 1
    assert "女子" not in windows[0].snippet
    assert "ド●ペリ" in windows[0].snippet
    messages = build_mask_restore_messages(windows)
    blob = messages[0]["content"] + messages[1]["content"]
    assert "女子●生" not in blob
    assert "여고생" not in blob
    assert "쇼타" not in blob


def test_restore_is_idempotent():
    once = restore_censored_text("レ×プ輪● 奴●契約")
    twice = restore_censored_text(once.text)
    assert twice.text == once.text
    assert twice.terms == ()


def test_accept_mask_restore_rejects_loose_edits():
    assert accept_mask_restore("ド●ペリ", "ドンペリ", "high") == "ドンペリ"
    assert accept_mask_restore("ド●ペリ", "ドンペリ", "low") is None
    assert accept_mask_restore("ド●ペリ", "ドンペリ!", "high") is None
    assert accept_mask_restore("ド●ペリ", "ド○ペリ", "high") is None
    assert accept_mask_restore("荒●区日●里", "荒川区日暮里", "high") == "荒川区日暮里"
    assert accept_mask_restore("荒●区日●里", "荒川市日暮里", "high") is None


def test_apply_restore_response_keeps_rejected_masks():
    windows = collect_restore_windows("ド●ペリと荒●区", "")
    assert len(windows) == 1
    snippet = windows[0].snippet
    restored = snippet.replace("●", "ン", 1).replace("●", "川", 1)
    title, synopsis, applied = apply_restore_response(
        "ド●ペリと荒●区",
        "",
        windows,
        {"0": (restored, "high")},
    )
    assert "●" not in title
    assert synopsis == ""
    assert applied == ((snippet, restored),)

    kept, _, rejected = apply_restore_response(
        "ド●ペリと荒●区",
        "",
        windows,
        {"0": (restored, "low")},
    )
    assert kept == "ド●ペリと荒●区"
    assert rejected == ()


def test_prompt_uses_restored_title_and_mandatory_terms():
    messages = build_metadata_translation_messages(
        "ABC-123",
        "レ×プ輪● 家庭●師 強●羞恥",
        "犯●れて 夜●い",
    )
    system = messages[0]["content"]
    payload = json.loads(messages[1]["content"].removesuffix("\n\n/no_think"))

    assert "強姦 is 강간" in system
    assert payload["title"] == "レイプ輪姦 家庭教師 強制羞恥"
    assert payload["synopsis"] == "犯されて 夜這い"
    assert payload["title_before_mask_restore"].startswith("レ×プ")
    kos = {item["ko"] for item in payload["mandatory_terms"]}
    assert {"강간", "윤간", "가정교사", "강제 수치", "범해져서", "야바이"} <= kos
    assert "여고생" not in system
    assert "쇼타" not in system
    assert "여고생" not in messages[1]["content"]
    assert "쇼타" not in messages[1]["content"]


class _Router:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    async def route(self, messages, tier_override=None, json_mode=False):
        self.calls.append({"messages": messages, "tier": tier_override, "json_mode": json_mode})
        return self.handler(messages)


@pytest.mark.anyio
async def test_fill_skips_the_model_when_nothing_is_eligible():
    router = _Router(lambda messages: "{}")
    title, synopsis, applied = await fill_unresolved_masks(
        router,
        "J●達",
        "シ●タ",
        tier={"max_tokens": 100},
        logger=lambda _msg: None,
    )
    assert router.calls == []
    assert title == "J●達"
    assert synopsis == "シ●タ"
    assert applied == ()


@pytest.mark.anyio
async def test_fill_applies_one_high_confidence_reply():
    def handler(messages):
        payload = json.loads(messages[1]["content"].removesuffix("\n\n/no_think"))
        items = []
        for item in payload["items"]:
            items.append(
                {
                    "id": item["id"],
                    "restored": item["snippet"].replace("●", "ン"),
                    "confidence": "high",
                }
            )
        return json.dumps({"items": items})

    router = _Router(handler)
    title, synopsis, applied = await fill_unresolved_masks(
        router,
        "ド●ペリ",
        "",
        tier={"max_tokens": 1024, "max_retries": 4, "temperature": 0.3},
        logger=lambda _msg: None,
    )
    assert title == "ドンペリ"
    assert synopsis == ""
    assert applied == (("ド●ペリ", "ドンペリ"),)
    assert router.calls[0]["tier"]["max_tokens"] == 256
    assert router.calls[0]["tier"]["max_retries"] == 1
    assert router.calls[0]["json_mode"] is True


@pytest.mark.anyio
async def test_fill_keeps_masks_when_the_model_fails():
    class Boom:
        async def route(self, messages, tier_override=None, json_mode=False):
            raise RuntimeError("down")

    title, synopsis, applied = await fill_unresolved_masks(
        Boom(),
        "ド●ペリ",
        "",
        tier={},
        logger=lambda _msg: None,
    )
    assert title == "ド●ペリ"
    assert synopsis == ""
    assert applied == ()
