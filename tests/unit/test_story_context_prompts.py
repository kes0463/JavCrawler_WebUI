from javstory.translation.story_context_prompts import (
    SYSTEM_STORY_CONTEXT_GROK,
    format_story_context_for_translation,
    render_story_context_user_message,
)


def test_story_context_prompt_forces_korean_descriptive_fields():
    assert "반드시 한국어로 작성" in SYSTEM_STORY_CONTEXT_GROK
    assert "synopsis_short" in SYSTEM_STORY_CONTEXT_GROK
    assert "overall_summary" in SYSTEM_STORY_CONTEXT_GROK
    assert "scene_summary" in SYSTEM_STORY_CONTEXT_GROK
    assert "tone" in SYSTEM_STORY_CONTEXT_GROK
    assert "일본어 웹 자료를 찾았더라도" in SYSTEM_STORY_CONTEXT_GROK


def test_story_context_user_message_repeats_language_constraint():
    msg = render_story_context_user_message(product_code="PRED-250")
    assert "PRED-250" in msg
    assert "반드시 한국어로 작성" in msg
    assert "title_ja" in msg
    assert "key_tags" in msg


def test_format_story_context_compact_omits_scene_body():
    data = {
        "verification_ok": True,
        "product_code": "GVH-684",
        "title_ja": "母子姦",
        "title_ko": "모자간",
        "actress": "宝田もなみ",
        "maker": "Glory Quest",
        "release_date": "2024-09-07",
        "synopsis_short": "아들이 어머니를 목격한 뒤 집착한다." * 8,
        "overall_summary": "장황한 전체 요약입니다. " * 40,
        "scenes": [
            {
                "scene_id": "S01",
                "time_range": "00:00:00 ~ 00:18:00",
                "scene_label": "목격",
                "scene_summary": "아주 긴 씬 요약이 여기에 들어간다. " * 20,
                "tone": "긴장",
                "key_tags": ["incest", "milf"],
            }
        ],
    }
    full = format_story_context_for_translation(data)
    compact = format_story_context_for_translation(data, compact=True, max_chars=900)
    assert "아주 긴 씬 요약" in full
    assert "아주 긴 씬 요약" not in compact
    assert "S01" in compact
    assert len(compact) < len(full)
    assert len(compact) <= 900
