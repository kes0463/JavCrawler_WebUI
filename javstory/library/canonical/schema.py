"""
작품 단위 canonical 저장소 스키마.

- Grok story JSON(story_context_prompts 호환) 필드를 편집·보호 플래그·수치 구간·스틸 경로와 결합한다.
- 단일 진실 소스: {library_root}/{품번}/library_state.json
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from javstory.library.stills.time_range import parse_time_range

# canonical 파일(JSON) 최상위 schema_version — Grok 출력의 schema_version과 별개
CANONICAL_SCHEMA_VERSION = 1

# export 번들 메타( master_db.js / story JSON )와 동기화 검사용
DEFAULT_EXPORT_VERSION = "export_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ExportManifest:
    """내보낸 산출물 버전·지문 — 외부 파일 직접 수정 시 불일치 감지에 사용."""

    export_version: str = DEFAULT_EXPORT_VERSION
    generated_at: str = ""
    story_json_relpath: str | None = None
    master_db_relpath: str | None = None
    # relpath (라이브러리 루트 또는 프로젝트 루트 기준) -> {sha256, mtime_iso}
    file_fingerprints: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = utc_now_iso()


@dataclass
class VideoPartRef:
    """분할 영상 한 파트 — 순서·상대 경로·길이(캐시)."""

    order: int = 0
    video_relpath: str = ""
    duration_sec: float | None = None


@dataclass
class MediaBinding:
    """로컬 영상 등 — 절대 경로 대신 루트 기준 상대 경로 권장."""

    primary_video_relpath: str | None = None
    notes: str = ""
    parts: list[VideoPartRef] = field(default_factory=list)
    #: 번역·참고용 합산 SRT(파트별 동명 SRT와 별도)
    merged_timeline_srt_relpath: str | None = None


@dataclass
class SceneEntry:
    """
    씬 한 줄 — Grok scenes[] 항목 + canonical 확장.

    locked_fields: 사용자가 확정한 필드 이름 집합. Grok 재실행 시 해당 키는 덮어쓰지 않음.
    (예: time_range, scene_summary, scene_label, tone, key_tags)
    """

    scene_id: str
    time_range: str
    scene_label: str = ""
    scene_summary: str = ""
    tone: str = ""
    key_tags: list[str] = field(default_factory=list)
    time_label: str = ""

    start_sec: float | None = None
    end_sec: float | None = None
    still_paths: list[str] = field(default_factory=list)
    locked_fields: set[str] = field(default_factory=set)
    needs_still_refresh: bool = False

    def to_json_dict(self) -> dict[str, Any]:
        d = {
            "scene_id": self.scene_id,
            "time_range": self.time_range,
            "scene_label": self.scene_label,
            "scene_summary": self.scene_summary,
            "tone": self.tone,
            "key_tags": list(self.key_tags),
            "time_label": self.time_label or self.time_range,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "still_paths": list(self.still_paths),
            "locked_fields": sorted(self.locked_fields),
            "needs_still_refresh": self.needs_still_refresh,
        }
        return d

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> SceneEntry:
        lf = d.get("locked_fields") or []
        if isinstance(lf, str):
            lf = [lf]
        locked = set(lf) if isinstance(lf, list) else set()
        tags = d.get("key_tags") or []
        if not isinstance(tags, list):
            tags = []
        return cls(
            scene_id=str(d.get("scene_id", "")),
            time_range=str(d.get("time_range", "")),
            scene_label=str(d.get("scene_label", "")),
            scene_summary=str(d.get("scene_summary", "")),
            tone=str(d.get("tone", "")),
            key_tags=[str(x) for x in tags],
            time_label=str(d.get("time_label", "") or d.get("time_range", "")),
            start_sec=_opt_float(d.get("start_sec")),
            end_sec=_opt_float(d.get("end_sec")),
            still_paths=[str(x) for x in (d.get("still_paths") or [])],
            locked_fields=locked,
            needs_still_refresh=bool(d.get("needs_still_refresh", False)),
        )


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class LibraryCanonical:
    """
    작품 단위 편집 가능 상태 — Grok 호환 메타 + 씬 배열 + 보호·export 메타.

    work_locked_fields: 작품 전역 필드 보호 (예: title_ko, overall_summary, synopsis_short)
    """

    canonical_schema_version: int = CANONICAL_SCHEMA_VERSION
    product_code: str = ""

    schema_version: int | None = None
    verification_ok: bool | None = None
    code_mismatch: bool | None = None
    mismatch_reason: str = ""
    title_ja: str = ""
    title_ko: str = ""
    actress: str = ""
    maker: str = ""
    release_date: str = ""
    synopsis_short: str = ""
    overall_summary: str = ""
    scenes: list[SceneEntry] = field(default_factory=list)

    work_locked_fields: set[str] = field(default_factory=set)
    media: MediaBinding | None = None
    export_manifest: ExportManifest | None = None

    # 작품 단위 번역 노트 — Gemini 번역 프롬프트의 {{note}}에 주입.
    # 권장 섹션: [작품 기본 컨텍스트], [화자 프로필 및 관계],
    # [Whisper AI 오인식 교정 사전], [용어/은어 매핑], [고정 표기/호칭 사전]
    translation_note: str = ""

    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = utc_now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_json_dict(self) -> dict[str, Any]:
        media_d = None
        if self.media is not None:
            media_d = {
                "primary_video_relpath": self.media.primary_video_relpath,
                "notes": self.media.notes,
                "merged_timeline_srt_relpath": self.media.merged_timeline_srt_relpath,
                "parts": [
                    {
                        "order": p.order,
                        "video_relpath": p.video_relpath,
                        "duration_sec": p.duration_sec,
                    }
                    for p in self.media.parts
                ],
            }
        exp = None
        if self.export_manifest is not None:
            exp = asdict(self.export_manifest)
        return {
            "canonical_schema_version": self.canonical_schema_version,
            "product_code": self.product_code,
            "schema_version": self.schema_version,
            "verification_ok": self.verification_ok,
            "code_mismatch": self.code_mismatch,
            "mismatch_reason": self.mismatch_reason,
            "title_ja": self.title_ja,
            "title_ko": self.title_ko,
            "actress": self.actress,
            "maker": self.maker,
            "release_date": self.release_date,
            "synopsis_short": self.synopsis_short,
            "overall_summary": self.overall_summary,
            "scenes": [s.to_json_dict() for s in self.scenes],
            "work_locked_fields": sorted(self.work_locked_fields),
            "media": media_d,
            "export_manifest": exp,
            "translation_note": self.translation_note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> LibraryCanonical:
        wf = d.get("work_locked_fields") or []
        if isinstance(wf, str):
            wf = [wf]
        work_locked = set(wf) if isinstance(wf, list) else set()

        scenes_raw = d.get("scenes") or []
        scenes: list[SceneEntry] = []
        if isinstance(scenes_raw, list):
            for item in scenes_raw:
                if isinstance(item, dict):
                    scenes.append(SceneEntry.from_json_dict(item))

        media = None
        m = d.get("media")
        if isinstance(m, dict):
            parts_raw = m.get("parts") or []
            parts_list: list[VideoPartRef] = []
            if isinstance(parts_raw, list):
                for pr in parts_raw:
                    if not isinstance(pr, dict):
                        continue
                    parts_list.append(
                        VideoPartRef(
                            order=int(pr.get("order", 0)),
                            video_relpath=str(pr.get("video_relpath", "")),
                            duration_sec=_opt_float(pr.get("duration_sec")),
                        )
                    )
            media = MediaBinding(
                primary_video_relpath=m.get("primary_video_relpath"),
                notes=str(m.get("notes", "")),
                parts=parts_list,
                merged_timeline_srt_relpath=m.get("merged_timeline_srt_relpath"),
            )

        exp = None
        em = d.get("export_manifest")
        if isinstance(em, dict):
            exp = ExportManifest(
                export_version=str(em.get("export_version", DEFAULT_EXPORT_VERSION)),
                generated_at=str(em.get("generated_at", "")),
                story_json_relpath=em.get("story_json_relpath"),
                master_db_relpath=em.get("master_db_relpath"),
                file_fingerprints=dict(em.get("file_fingerprints") or {}),
            )

        sv = d.get("schema_version")
        schema_v = int(sv) if sv is not None and str(sv).isdigit() else None

        return cls(
            canonical_schema_version=int(d.get("canonical_schema_version", CANONICAL_SCHEMA_VERSION)),
            product_code=str(d.get("product_code", "")),
            schema_version=schema_v,
            verification_ok=d.get("verification_ok"),
            code_mismatch=d.get("code_mismatch"),
            mismatch_reason=str(d.get("mismatch_reason", "")),
            title_ja=str(d.get("title_ja", "")),
            title_ko=str(d.get("title_ko", "")),
            actress=str(d.get("actress", "")),
            maker=str(d.get("maker", "")),
            release_date=str(d.get("release_date", "")),
            synopsis_short=str(d.get("synopsis_short", "")),
            overall_summary=str(d.get("overall_summary", "")),
            scenes=scenes,
            work_locked_fields=work_locked,
            media=media,
            export_manifest=exp,
            translation_note=str(d.get("translation_note", "") or ""),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
        )


def library_canonical_from_grok_dict(grok: dict[str, Any]) -> LibraryCanonical:
    """Grok story JSON(dict)만으로 초기 canonical — 보호 필드는 비어 있음."""
    scenes_out: list[SceneEntry] = []
    raw_scenes = grok.get("scenes") or []
    if isinstance(raw_scenes, list):
        for item in raw_scenes:
            if not isinstance(item, dict):
                continue
            tr = str(item.get("time_range", ""))
            a_sec, b_sec = parse_time_range(tr)
            scenes_out.append(
                SceneEntry(
                    scene_id=str(item.get("scene_id", "")),
                    time_range=tr,
                    scene_label=str(item.get("scene_label", "")),
                    scene_summary=str(item.get("scene_summary", "")),
                    tone=str(item.get("tone", "")),
                    key_tags=[str(x) for x in (item.get("key_tags") or []) if x is not None],
                    time_label=str(item.get("time_label", "") or tr),
                    start_sec=a_sec,
                    end_sec=b_sec,
                    needs_still_refresh=True,
                )
            )

    sv = grok.get("schema_version")
    schema_v = int(sv) if sv is not None and str(sv).isdigit() else None

    return LibraryCanonical(
        product_code=str(grok.get("product_code", "")),
        schema_version=schema_v,
        verification_ok=grok.get("verification_ok"),
        code_mismatch=grok.get("code_mismatch"),
        mismatch_reason=str(grok.get("mismatch_reason", "")),
        title_ja=str(grok.get("title_ja", "")),
        title_ko=str(grok.get("title_ko", "")),
        actress=str(grok.get("actress", "")),
        maker=str(grok.get("maker", "")),
        release_date=str(grok.get("release_date", "")),
        synopsis_short=str(grok.get("synopsis_short", "")),
        overall_summary=str(grok.get("overall_summary", "")),
        scenes=scenes_out,
    )


def grok_story_dict_from_canonical(state: LibraryCanonical) -> dict[str, Any]:
    """번역 힌트 등 기존 파이프라인과 호환되도록 Grok 형태 dict 생성."""
    return {
        "schema_version": state.schema_version if state.schema_version is not None else 1,
        "product_code": state.product_code,
        "verification_ok": state.verification_ok if state.verification_ok is not None else True,
        "code_mismatch": state.code_mismatch if state.code_mismatch is not None else False,
        "mismatch_reason": state.mismatch_reason,
        "title_ja": state.title_ja,
        "title_ko": state.title_ko,
        "actress": state.actress,
        "maker": state.maker,
        "release_date": state.release_date,
        "synopsis_short": state.synopsis_short,
        "overall_summary": state.overall_summary,
        "scenes": [
            {
                "scene_id": s.scene_id,
                "time_range": s.time_range,
                "scene_label": s.scene_label,
                "scene_summary": s.scene_summary,
                "tone": s.tone,
                "key_tags": list(s.key_tags),
            }
            for s in state.scenes
        ],
    }
