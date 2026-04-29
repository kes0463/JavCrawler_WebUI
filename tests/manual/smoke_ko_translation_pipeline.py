r"""
한국어 번역 파이프라인 스모크 테스트.

사전 조건:
- OpenRouter: `.env`의 OPENROUTER_API_KEY 또는 Windows 자격 증명(keyring)에 키 저장.
- 번역 모델: `JAVSTORY_TRANSLATION_PROFILE` — default(v3.2 NT), keeper(GLM 5.1), deepseek_chat(deepseek-chat), budget(Ollama·gemma4:e4b 기본), qwen35(qwen3.5:9b), qwen3_14(qwen3:14b). 또는 `JAVSTORY_TRANSLATION_OPENROUTER_MODEL` / `JAVSTORY_TRANSLATION_OLLAMA_MODEL` / `JAVSTORY_TRANSLATION_PROVIDER=ollama`로 직접 지정.
- Ollama: `JAVSTORY_TRANSLATION_PROFILE=budget|qwen35|qwen3_14|gemma3_12` 또는 `JAVSTORY_TRANSLATION_PROVIDER=ollama`, 로컬 Ollama 및 모델 준비.
- 배경 JSON: `get_or_build_background`가 DB 메타를 쓰므로 `product_code`에 해당하는 `jav_metadata` 행이 있으면 좋음(없어도 빈 메타로 시도).

예시 (번역만, 교정 생략 — `ja_srt_path` 없이 입력 SRT만 지정):

  python Test\manual\smoke_ko_translation_pipeline.py ^
    --translate-ja path\\to\\file.ja.srt ^
    --product-code ABC-123 ^
    --work-dir path\\to\\out_dir

예시 (교정 포함 — `ja_srt_path`를 주면 교정 후 번역 입력은 교정본 우선):

  python Test\manual\smoke_ko_translation_pipeline.py ^
    --ja-srt path\\to\\file.ja.srt ^
    --product-code ABC-123 ^
    --work-dir path\\to\\out_dir

비용 절감(Ollama) 번역 예:

  set JAVSTORY_TRANSLATION_PROFILE=budget
  python Test\manual\smoke_ko_translation_pipeline.py --translate-ja sample.ja.srt --product-code TEST-001 --work-dir .\\tmp_ko_test

스토리 맥락(Grok 웹 전용, 품번 검증·캐시) + 번역 LLM 전체 프롬프트 로그(테스트용):

  python Test\manual\smoke_ko_translation_pipeline.py ^
    --translate-ja sample.ja.srt --product-code TEST-001 --work-dir .\\tmp_ko_test ^
    --enable-story --log-story --log-full-prompt

  캐시 무시 재조회: --force-story-context 또는 환경변수 JAVSTORY_STORY_CONTEXT_FORCE=1
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.config import secrets_manager
from javstory.llm.engine import MultiTierRouter

secrets_manager.apply_env_to_os()


async def _run(args: argparse.Namespace) -> None:
    api_key = secrets_manager.get_openrouter_api_key() or ""
    if not api_key and (not args.translation_provider or args.translation_provider != "ollama"):
        print(
            "[test] 경고: OpenRouter API 키가 없습니다. "
            "Ollama만 쓰려면 --translation-provider ollama 를 주세요.",
        )
    router = MultiTierRouter(api_key=api_key, logger_func=print)

    from javstory.translation.subtitle_pipeline_orchestrator import SubtitlePipelineOrchestrator

    orch = SubtitlePipelineOrchestrator(router)
    kwargs: dict = {
        "product_code": args.product_code,
        "work_dir": str(Path(args.work_dir).resolve()),
        "logger_func": print,
    }
    if args.ja_srt:
        kwargs["ja_srt_path"] = str(Path(args.ja_srt).resolve())
    if args.translate_ja:
        kwargs["translate_ja_srt_path"] = str(Path(args.translate_ja).resolve())
    if args.ko_srt:
        kwargs["ko_srt_path"] = str(Path(args.ko_srt).resolve())
    if args.translation_provider:
        kwargs["translation_provider"] = args.translation_provider
    if args.force_rebuild_background:
        kwargs["force_rebuild"] = True
    if args.enable_story:
        kwargs["enable_story_context"] = True
    elif args.no_story:
        kwargs["enable_story_context"] = False
    if args.log_story:
        kwargs["log_story_context_report"] = True
    if args.log_full_prompt:
        kwargs["log_full_translation_prompt"] = True
    if args.force_story_context:
        kwargs["force_rebuild_story_context"] = True

    print("[test] run_for_product kwargs:", {k: kwargs[k] for k in sorted(kwargs)})
    await orch.run_for_product(args.product_code, **kwargs)
    print("[test] 완료. work_dir에서 .ko.srt 확인.")


def main() -> None:
    p = argparse.ArgumentParser(description="KO 번역 파이프라인 스모크")
    p.add_argument("--product-code", default="TEST-001", help="jav_metadata 조회·배경 캐시용 품번")
    p.add_argument("--work-dir", required=True, help="출력 폴더 (.ko.srt 등)")
    p.add_argument("--ja-srt", help="일본어 원본 SRT (주면 교정 단계 실행)")
    p.add_argument(
        "--translate-ja",
        help="번역에 쓸 JA SRT (교정 생략 시 필수). 교정과 함께 쓰면 이 경로가 우선",
    )
    p.add_argument("--ko-srt", help="한국어 출력 경로(선택, 기본은 work_dir/{stem}.ko.srt)")
    p.add_argument(
        "--translation-provider",
        choices=("openrouter", "ollama"),
        help="미지정 시 환경변수 JAVSTORY_TRANSLATION_PROVIDER",
    )
    p.add_argument(
        "--force-rebuild-background",
        action="store_true",
        help="배경 JSON 강제 재생성",
    )
    p.add_argument(
        "--enable-story",
        action="store_true",
        help="스토리 맥락 리포트 단계 강제 실행(Grok 웹검색 전용·품번만, OPENROUTER_API_KEY 필요)",
    )
    p.add_argument(
        "--force-story-context",
        action="store_true",
        help="스토리 맥락 디스크 캐시 무시 후 API 재호출",
    )
    p.add_argument(
        "--no-story",
        action="store_true",
        help="스토리 맥락 리포트 단계 끄기",
    )
    p.add_argument(
        "--log-story",
        action="store_true",
        help="콘솔에 스토리 맥락 리포트 본문 출력(디버그)",
    )
    p.add_argument(
        "--log-full-prompt",
        action="store_true",
        help="GLM 번역 호출마다 system+user 전체 프롬프트 로그",
    )
    args = p.parse_args()
    if not args.ja_srt and not args.translate_ja:
        p.error("--ja-srt 또는 --translate-ja 중 하나는 필요합니다.")
    if args.enable_story and args.no_story:
        p.error("--enable-story 와 --no-story 는 함께 쓸 수 없습니다.")

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
