from javstory.translation.story_context_prompts import (
    SYSTEM_STORY_CONTEXT_GROK,
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
