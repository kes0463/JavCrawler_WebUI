"""Manual crawl test for actress single/multi cases."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from javstory.harvest.crawler import HybridJavCrawler
from javstory.harvest.database import get_db_session_ctx
from javstory.utils.actress_resolver import ActressResolver, dedupe_crawled_actor_names


async def test_code(code: str) -> dict:
    crawler = HybridJavCrawler()
    raw = await crawler.fetch_metadata_smart(code.upper())
    actors = raw.get("actors") or []
    if isinstance(actors, str):
        actors = [a.strip() for a in actors.split(",") if a.strip()]

    with get_db_session_ctx() as session:
        deduped = dedupe_crawled_actor_names(
            session,
            [str(a).strip() for a in actors if str(a).strip()],
        )

    resolved = ActressResolver().resolve_names(deduped)

    return {
        "product_code": code.upper(),
        "sources_tried": raw.get("_sources_tried"),
        "sources_used": raw.get("_sources_used"),
        "raw_actors": actors,
        "deduped_crawl": deduped,
        "resolved_ko": resolved.get("ko"),
        "resolved_ja": resolved.get("ja"),
        "title": raw.get("title"),
    }


async def main() -> None:
    codes = ["SNOS-257", "DAZD-264"]
    results = []
    for code in codes:
        print(f"\n=== Crawling {code} ===", flush=True)
        try:
            r = await test_code(code)
            results.append(r)
        except Exception as e:
            results.append({"product_code": code, "error": str(e)})

    out_path = ROOT / "tests" / "manual" / "_crawl_actress_test_result.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
