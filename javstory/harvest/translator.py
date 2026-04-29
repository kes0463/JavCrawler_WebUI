import json
import keyring
from typing import Optional
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.llm.engine import MultiTierRouter
from javstory.config.app_config import KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER, harvest_translation_llm_tier

class MetadataTranslator:
    """
    [Phase 5] 제목·시놉시스 전용 일본어→한국어 번역 엔진.
    - 배우·장르·메이커는 DB 마스터(리졸버)로만 저장하며 LLM이 건드리지 않는다.
    - DeepSeek V3 -> Hermes fallback 파이프라인 사용.
    - 성인 콘텐츠 특화 프롬프트 적용 (검열 회피 및 로컬라이징).
    """

    def __init__(self, api_key: Optional[str] = None, logger_func=None):
        if not api_key:
            api_key = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER)
        
        self.logger = logger_func if logger_func else print
        self.router = MultiTierRouter(api_key, logger_func=self.logger) if api_key else None

    async def translate_metadata_batch(self, product_code: str, title: str, synopsis: str, actors: list = [], genres: list = [], maker: str = "", approved_terms: dict = {}) -> dict:
        """한 번의 AI 호출로 제목·시놉시스를 일본어 정제 + 한국어로만 변환. (배우/장르/제작사는 DB 테이블에서만 처리)"""
        if not self.router:
            return {}

        system_prompt = """# Role
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
   - Light cleanup / normalization only; keep meaning. Infer censored/masked expressions where standard for the genre.
5. **Censored Kanji Inference** in titles: infer full sense where masking is used (e.g. レ×プ).

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
        user_content = {
            "product_code": product_code,
            "title": title,
            "synopsis": synopsis,
            "context_actors": actors,
            "context_genres": genres,
            "context_maker": maker,
            "approved_terminology": approved_terms,
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)}
        ]

        try:
            raw_res = await self.router.route(messages, tier_override=harvest_translation_llm_tier())
            json_str = self._extract_json(raw_res)
            return json.loads(json_str)
        except Exception as e:
            self.logger(f"[Translator] 일괄 번역 실패 ({product_code}): {e}")
            return {}

    def _extract_json(self, text: str) -> str:
        """텍스트에서 JSON 부분만 추출 (마크다운 가드 등 제거)"""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return text.strip()

    async def close(self) -> None:
        """사용된 비동기 라우터 리소스를 해제합니다."""
        if self.router:
            await self.router.close()

