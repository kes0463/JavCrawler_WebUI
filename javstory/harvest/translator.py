import asyncio
import json
import keyring
from typing import Optional
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.llm.engine import MultiTierRouter
from javstory.config.app_config import (
    KEYRING_SERVICE_NAME,
    KEYRING_ACCOUNT_OPENROUTER,
    harvest_translation_llm_tier,
    harvest_translation_timeout_sec,
)
from javstory.utils.common import safe_console_print
from javstory.harvest.censored_terms import (
    apply_restore_response,
    build_mask_restore_messages,
    collect_restore_windows,
    dedupe_terms,
    parse_restore_items,
    restore_censored_text,
)

_METADATA_SYSTEM_PROMPT = """# Role
You are a professional JAV (Japanese Adult Video) localization expert with 15+ years of experience.
Your only task: refine Japanese **title** and **synopsis**, and write natural **Korean** versions.
Do not output any language other than Japanese and Korean. Actress/genre/maker lists in the user JSON are **only** for name consistency inside title/synopsis; you do **not** output them.

# Core Rules
1. **No Censorship**: MAINTAIN the original erotic, provocative, and explicit tone. NEVER censor sexual expressions or slang.
2. **Natural Korean (title_ko, synopsis_ko)**: "한국 정서에 맞는 유려하고 자극적인 문체 (번역투 금지)"
2.1 **Korean-only guardrails (CRITICAL, KO output must follow)**:
   - **No abnormal multilingual mixing**: Korean must be natural Korean. Do NOT inject random EN/ZH/JP fragments into Korean sentences, except community-standard terms (e.g. "NTR", "TS", "스와핑", "SM") when appropriate.
   - **Fix Japanese-isms**: Japanese passive → natural Korean where it reads better. Avoid clunky "그/그녀" overuse and overusing "~의".
   - **Genre / slang**: For adult-subculture terms, use what Korean communities actually use, not literal dictionary glosses.
   - **Dialogue in synopsis**: Keep honorifics / speech level consistent (do not mix 존댓말/반말 randomly).
3. **Approved Terminology (CRITICAL)** for Korean title/synopsis:
   - Use the provided "approved_terminology"."ko" mappings whenever those Japanese names (actresses, makers, known genres) appear: use the **Korean** value, not ad-hoc transliteration.
4. **Japanese refinery (title_ja, synopsis_ja)**:
   - Light cleanup / normalization only; keep meaning. Known masks are already restored in `title` / `synopsis`. Copy any remaining ● ○ × through unchanged. Do not guess the hidden character.
5. **Masked compounds (mandatory_terms)**:
   - Translate `title` and `synopsis`, not `title_before_mask_restore` / `synopsis_before_mask_restore`.
   - When `mandatory_terms` is present, each `ja` word MUST use that `ko`. Do not soften the word into a bland adjective.
   - 強姦 is 강간, never 강한. 強姦される is 강간당하다. A word that starts with 強制 is 강제, not 강간.
   - 逆レイプ is 역강간. 輪姦 is 윤간. 痴漢 is 치한. レイプ is 강간.
   - チンポ / ちんぽ is 자지. マンコ / まんこ / おまんこ / オマンコ is 보지. 口マンコ / 口まんこ is 입보지.
   - 奴隷 is 노예. 奴隷契約 is 노예 계약. 家庭教師 is 가정교사. 夜這い is 야바이.
   - 犯されて is 범해져서. 犯された is 범해진. 犯され is 범해져.
   - 昏睡 is 혼수. 凌辱 is 능욕. 媚薬 is 미약.
   - Conjugate endings naturally around those words. Keep names that are part of the source title.

# Output Format
Return ONLY a valid JSON object. No markdown code blocks.
**Exactly these four keys (no other keys):**

{
  "title_ja": "Refined or normalized Japanese title (same line of meaning as source)",
  "title_ko": "한국어 제목",
  "synopsis_ja": "Refined or cleaned Japanese synopsis",
  "synopsis_ko": "한국어 시놉시스"
}
"""


def build_metadata_translation_messages(
    product_code: str,
    title: str,
    synopsis: str,
    actors: list | None = None,
    genres: list | None = None,
    maker: str = "",
    approved_terms: dict | None = None,
    *,
    title_restored: str | None = None,
    synopsis_restored: str | None = None,
    terms: tuple[tuple[str, str], ...] | None = None,
) -> list[dict]:
    """Build the harvest title/synopsis prompt with masks already restored."""
    title_src = title or ""
    synopsis_src = synopsis or ""
    if title_restored is None:
        title_restored = restore_censored_text(title_src).text
    if synopsis_restored is None:
        synopsis_restored = restore_censored_text(synopsis_src).text
    if terms is None:
        terms = dedupe_terms(
            restore_censored_text(title_src).terms,
            restore_censored_text(synopsis_src).terms,
        )
    user_content: dict = {
        "product_code": product_code,
        "title": title_restored,
        "synopsis": synopsis_restored,
        "context_actors": actors or [],
        "context_genres": genres or [],
        "context_maker": maker,
        "approved_terminology": approved_terms or {},
    }
    if title_restored != title_src:
        user_content["title_before_mask_restore"] = title_src
    if synopsis_restored != synopsis_src:
        user_content["synopsis_before_mask_restore"] = synopsis_src
    if terms:
        user_content["mandatory_terms"] = [{"ja": ja, "ko": ko} for ja, ko in terms]

    return [
        {"role": "system", "content": _METADATA_SYSTEM_PROMPT},
        {
            "role": "user",
            # /no_think: Qwen3 계열은 기본적으로 답변 전에 내부 사고(thinking) 블록을
            # 먼저 생성함 — JSON 출력만 필요한 번역 작업엔 불필요하고, 그 사고 과정에
            # 토큰/시간 예산을 다 써버려 실제 JSON(특히 마지막 synopsis_ko 필드)이
            # 타임아웃에 잘리는 원인이었다. Qwen3 공식 컨벤션으로 억제.
            "content": json.dumps(user_content, ensure_ascii=False) + "\n\n/no_think",
        },
    ]


def _extract_json_text(text: str) -> str:
    text = (text or "").strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


async def fill_unresolved_masks(
    router,
    title: str,
    synopsis: str,
    *,
    tier: dict,
    logger,
    timeout_sec: float = 30.0,
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """One short call for masks the rule list did not cover. Failures keep the mask."""
    windows = collect_restore_windows(title, synopsis)
    if not windows:
        return title or "", synopsis or "", ()
    restore_tier = dict(tier)
    restore_tier["max_tokens"] = 256
    restore_tier["max_retries"] = 1
    restore_tier["temperature"] = 0.0
    try:
        raw = await asyncio.wait_for(
            router.route(
                build_mask_restore_messages(windows),
                tier_override=restore_tier,
                json_mode=True,
            ),
            timeout=timeout_sec,
        )
        parsed = json.loads(_extract_json_text(raw), strict=False)
    except Exception as exc:
        logger(f"[Translator] 잔여 마스크 복원 생략: {type(exc).__name__}: {exc}")
        return title or "", synopsis or "", ()
    return apply_restore_response(title, synopsis, windows, parse_restore_items(parsed))


class MetadataTranslator:
    """
    [Phase 5] 제목·시놉시스 전용 일본어→한국어 번역 엔진.
    - 배우·장르·메이커는 DB 마스터(리졸버)로만 저장하며 LLM이 건드리지 않는다.
    - DeepSeek V3 -> Hermes fallback 파이프라인 사용 (OpenRouter tier).
    - 기본: llama.cpp Gemma-4-E4B (`harvest_translation_llm_tier`).
    - 성인 콘텐츠 특화 프롬프트 적용 (검열 회피 및 로컬라이징).
    """

    def __init__(self, api_key: Optional[str] = None, logger_func=None):
        if not api_key:
            api_key = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER)

        self.logger = logger_func if logger_func else safe_console_print
        # llama.cpp / Ollama는 OpenRouter 키 없이도 동작
        self.router = MultiTierRouter(api_key or "local", logger_func=self.logger)

    async def translate_metadata_batch(self, product_code: str, title: str, synopsis: str, actors: list = [], genres: list = [], maker: str = "", approved_terms: dict = {}) -> dict:
        """규칙 복원 후, 남은 마스크만 짧게 복원하고 제목·시놉시스는 한 번만 번역한다."""
        title_src = title or ""
        synopsis_src = synopsis or ""
        ruled_title = restore_censored_text(title_src)
        ruled_synopsis = restore_censored_text(synopsis_src)
        terms = dedupe_terms(ruled_title.terms, ruled_synopsis.terms)
        if terms:
            shown = ", ".join(f"{ja}→{ko}" for ja, ko in terms)
            self.logger(f"[Translator] {product_code} 검열 규칙: {shown}")

        tier = harvest_translation_llm_tier()
        final_title, final_synopsis, filled = await fill_unresolved_masks(
            self.router,
            ruled_title.text,
            ruled_synopsis.text,
            tier=tier,
            logger=self.logger,
        )
        if filled:
            shown = ", ".join(f"{src}→{dst}" for src, dst in filled)
            self.logger(f"[Translator] {product_code} 잔여 마스크 반영: {shown}")

        messages = build_metadata_translation_messages(
            product_code,
            title_src,
            synopsis_src,
            actors=actors,
            genres=genres,
            maker=maker,
            approved_terms=approved_terms,
            title_restored=final_title,
            synopsis_restored=final_synopsis,
            terms=terms,
        )

        # Outer hard budget so a stuck llama-server cannot freeze harvest forever.
        hard_timeout = float(tier.get("timeout") or harvest_translation_timeout_sec()) + 20.0
        self.logger(
            f"[Translator] {product_code} → {tier.get('provider')}:{tier.get('model')} "
            f"(timeout={tier.get('timeout')}s, max_tokens={tier.get('max_tokens')}, "
            f"retries={tier.get('max_retries', 1)})"
        )
        try:
            raw_res = await asyncio.wait_for(
                self.router.route(messages, tier_override=tier),
                timeout=hard_timeout,
            )
            json_str = _extract_json_text(raw_res)
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                # Local models sometimes emit literal newlines inside synopsis text
                # instead of escaping them as \n, which strict JSON rejects even
                # though the structure is otherwise fine — retry permissively.
                parsed = json.loads(json_str, strict=False)
            if not isinstance(parsed, dict):
                raise ValueError(f"번역 결과가 dict가 아님: {type(parsed).__name__}")
            return parsed
        except asyncio.TimeoutError:
            self.logger(
                f"[Translator] 일괄 번역 타임아웃 ({product_code}, {hard_timeout:.0f}s) — "
                "제목만 저장하고 계속합니다. "
                "JAVSTORY_HARVEST_TRANSLATION_MODEL 을 더 작은 모델로 바꾸거나 "
                "OpenRouter를 쓰면 빨라집니다."
            )
            return {}
        except Exception as e:
            self.logger(f"[Translator] 일괄 번역 실패 ({product_code}): {type(e).__name__}: {e}")
            return {}

    async def close(self) -> None:
        """사용된 비동기 라우터 리소스를 해제합니다."""
        if self.router:
            await self.router.close()

