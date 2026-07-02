from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")


class LibraryItem(BaseModel):
    id: int
    product_code: str
    title_ko: Optional[str] = None
    title_ja: Optional[str] = None
    actors_ko: Optional[str] = None
    actors_ja: Optional[str] = None
    genres_ko: Optional[str] = None
    genres_ja: Optional[str] = None
    maker_ko: Optional[str] = None
    cover_image_local_path: Optional[str] = None
    thumb_image_local_path: Optional[str] = None
    release_date: Optional[str] = None
    folder_path: Optional[str] = None
    is_hardcoded: bool = False
    is_mopa: bool = False
    analysis_status: Optional[str] = None
    metadata_manual: bool = False
    updated_at: Optional[datetime] = None
    scene_count: int = 0
    favorite_score: int = 0
    has_subtitle: bool = False
    has_hardcoded_subtitle: bool = False
    has_mosaic_removed: bool = False
    has_preview: bool = False
    preview_media: Optional[str] = None

    model_config = {"from_attributes": True}


class SceneSummary(BaseModel):
    scene_id: str
    time_range: str = ""
    scene_label: str = ""
    scene_summary: str = ""
    tone: str = ""
    key_tags: list[str] = []


class LibraryItemDetail(LibraryItem):
    folder_monitoring_paused: bool = False
    folder_binding_pending: bool = False
    synopsis_ko: Optional[str] = None
    synopsis_ja: Optional[str] = None
    synopsis_en: Optional[str] = None
    title_en: Optional[str] = None
    title_zh_cn: Optional[str] = None
    actors_romaji: Optional[str] = None
    actors_en: Optional[str] = None
    actors_zh_cn: Optional[str] = None
    genres_en: Optional[str] = None
    maker_ja: Optional[str] = None
    maker_en: Optional[str] = None
    cover_image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    overall_summary: Optional[str] = None
    scenes: list[SceneSummary] = []
    scenes_source: Optional[str] = None
    snapshot_count: int = 0


class LibraryListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[LibraryItem]


class LibraryStats(BaseModel):
    total: int
    with_metadata: int
    with_folder: int
    without_metadata: int


class LibraryGenreItem(BaseModel):
    name: str
    count: int


class LibraryItemUpdate(BaseModel):
    title_ko: str | None = None
    title_ja: str | None = None
    title_en: str | None = None
    synopsis_ko: str | None = None
    synopsis_ja: str | None = None
    synopsis_en: str | None = None
    actors_ko: str | None = None
    actors_ja: str | None = None
    actors_romaji: str | None = None
    actors_en: str | None = None
    genres_ko: str | None = None
    genres_ja: str | None = None
    maker_ko: str | None = None
    maker_ja: str | None = None
    maker_en: str | None = None
    release_date: str | None = None


class OpenFolderResponse(BaseModel):
    ok: bool
    path: Optional[str] = None
    message: Optional[str] = None


class FolderBindRequest(BaseModel):
    folder_path: str
    force: bool = False


class FolderBindResponse(BaseModel):
    ok: bool
    path: Optional[str] = None
    message: Optional[str] = None
    mismatch: bool = False
    detail: Optional[LibraryItemDetail] = None


class CoverUploadResponse(BaseModel):
    ok: bool
    path: Optional[str] = None
    message: Optional[str] = None
    detail: Optional[LibraryItemDetail] = None


class SubtitleTrack(BaseModel):
    index: int
    label: str
    filename: str
    ext: str = ""


class PlaybackPart(BaseModel):
    index: int
    filename: str
    resume_ms: int = 0
    needs_proxy: bool = False
    proxy_ready: bool = True
    proxy_reason: Optional[str] = None
    subtitle_tracks: list[SubtitleTrack] = []


class StreamPrepareResponse(BaseModel):
    ready: bool
    needs_proxy: bool = False
    status: str = "direct"
    proxy_reason: Optional[str] = None
    error: Optional[str] = None


class PlaybackInfo(BaseModel):
    product_code: str
    title: str = ""
    parts: list[PlaybackPart] = []


class SubtitleCueList(BaseModel):
    cues: list[dict] = []


class HarvestItem(BaseModel):
    id: str
    target: str
    product_code: Optional[str] = None
    status: str = "pending"
    progress: int = 0
    message: str = ""
    kind: str = "code"
    is_path: bool = False
    force_rebuild: bool = False
    staged: bool = False


class AddHarvestRequest(BaseModel):
    codes: list[str]
    auto_start: bool = False

    @field_validator("codes", mode="before")
    @classmethod
    def validate_codes(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("codes must be a list")
        if len(v) > 100:
            raise ValueError("too many codes (max 100 per request)")
        normalized: list[str] = []
        for raw in v:
            code = str(raw).strip().upper()
            if not code:
                continue
            if len(code) > 50:
                raise ValueError(f"code too long (max 50 chars): {code!r}")
            if not _CODE_RE.match(code):
                raise ValueError(f"invalid code format: {code!r}")
            from javstory.utils.product_code import is_plausible_harvest_code

            if not is_plausible_harvest_code(code):
                raise ValueError(f"invalid product code (need prefix + digits): {code!r}")
            normalized.append(code)
        if not normalized:
            raise ValueError("no valid codes provided")
        return normalized


class HarvestQueueResponse(BaseModel):
    items: list[HarvestItem]
    running: bool
    grok_enabled: bool = False
    planned: Optional[int] = None
    warnings: Optional[list[str]] = None
    folder_path: Optional[str] = None


class HarvestSettingsRequest(BaseModel):
    grok_enabled: bool


class FolderHarvestRequest(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        p = str(v or "").strip()
        if not p:
            raise ValueError("path is required")
        if len(p) > 500:
            raise ValueError("path too long")
        return p


class FolderHarvestBatchRequest(BaseModel):
    paths: list[str]

    @field_validator("paths", mode="before")
    @classmethod
    def validate_paths(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("paths must be a list")
        normalized = [str(p).strip() for p in v if str(p).strip()]
        if not normalized:
            raise ValueError("no valid paths provided")
        if len(normalized) > 200:
            raise ValueError("too many paths (max 200)")
        return normalized


class PickFoldersResponse(BaseModel):
    paths: list[str]
    cancelled: bool = False


class RecrawlRequest(BaseModel):
    codes: list[str]
    force: bool = True

    @field_validator("codes", mode="before")
    @classmethod
    def validate_recrawl_codes(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("codes must be a list")
        normalized = [str(c).strip().upper() for c in v if str(c).strip()]
        if not normalized:
            raise ValueError("no valid codes provided")
        return normalized


class FavoritesHarvestRequest(BaseModel):
    mode: str = "selected"  # selected | all | missing
    codes: Optional[list[str]] = None


class WatchStats(BaseModel):
    total: int
    completed: int
    completion_rate: float
    avg_rating: float
    rated_count: int
    watched_count: int
    total_watch_hours: float


class DashboardSummary(BaseModel):
    library: LibraryStats
    watch: WatchStats
    pending_count: int
    metadata_match_rate: float


class PendingItem(BaseModel):
    product_code: str
    title: str


class SystemMetrics(BaseModel):
    gpu_name: str
    gpu_usage_percent: int
    gpu_total_gb: float
    gpu_used_gb: float
    cpu_percent: int
    mem_percent: int
    mem_used_gb: float
    mem_total_gb: float
    cpu_model: str


class CancelPendingRequest(BaseModel):
    product_code: str


class PreviewQueueItem(BaseModel):
    id: str
    product_code: str
    status: str
    progress: int = 0
    message: str = ""
    attempts: int = 0
    activity: str = "idle"
    started_at_ms: int = 0
    updated_at_ms: int = 0
    elapsed_sec: int = 0
    segment_index: int = 0
    segment_total: int = 0
    source_position_sec: float = 0.0
    source_duration_sec: float = 0.0


class PreviewQueueStatus(BaseModel):
    pending_count: int = 0
    running_count: int = 0
    queued_count: int = 0
    completed_total: int = 0
    failed_total: int = 0
    worker_count: int = 1
    processing_state: str = "idle"
    last_activity_at_ms: int = 0
    seconds_since_activity: int = 0
    stall_threshold_sec: int = 120
    paused: bool = False
    harvest_paused: bool = False
    user_paused: bool = False
    items: list[PreviewQueueItem] = []


# ── Actress profile ──────────────────────────────────────────────────────────


class ActressListItem(BaseModel):
    id: int
    name_ko: str = ""
    name_ja: str = ""
    profile_image_url: str = ""
    user_score: float = 0.0
    is_favorite: bool = False
    genres: str = ""
    work_count: int = 0


class ActressListResponse(BaseModel):
    total: int
    page: int = 1
    per_page: int = 48
    items: list[ActressListItem]


class ActressSearchItem(BaseModel):
    id: int
    name_ko: str = ""
    name_ja: str = ""
    user_score: float = 0.0


class ActressResolveResponse(BaseModel):
    name: str
    actress_id: int | None = None


class ActressAliasItem(BaseModel):
    alias_id: int
    alias_name: str
    alias_type: str = "stage"
    is_primary: bool = False


class ActressGalleryImage(BaseModel):
    image_id: int | None = None
    image_url: str = ""
    thumb_url: str = ""
    image_url_raw: str = ""
    sort_order: int = 0


class ActressProfile(BaseModel):
    id: int
    name_ja: str = ""
    name_ko: str = ""
    name_en: str = ""
    romaji: str = ""
    profile_image_url: str = ""
    genres: str = ""
    user_score: float = 0.0
    profile_text: str = ""
    birth_date: str = ""
    height: int = 0
    bust: int = 0
    waist: int = 0
    hip: int = 0
    cup_size: str = ""
    debut_date: str = ""
    debut_date_raw: str = ""
    agency: str = ""
    is_favorite: bool = False
    favorite_intensity: float = 0.0
    memo: str = ""
    work_count: int = 0
    aliases: list[ActressAliasItem] = []
    gallery_images: list[ActressGalleryImage] = []
    library_refresh_pcs: list[str] = []


class ActressWorkItem(BaseModel):
    product_code: str
    title_ko: str = ""
    actors_ko: str = ""
    genres_ko: str = ""
    cover_path: str = ""
    cover_url: str = ""
    release_date: str = ""
    favorite_score: int = 0
    user_rating: int = 0
    user_liked: bool = False


class ActressWorksBundle(BaseModel):
    works: list[dict]
    genres: list[str]


class ActressCreateRequest(BaseModel):
    name_ko: str = ""
    name_ja: str = ""
    name_en: str = ""
    genres: str = ""
    profile_text: str = ""
    memo: str = ""
    user_score: float = 0.0


class ActressUpdateRequest(BaseModel):
    name_ko: str | None = None
    name_ja: str | None = None
    name_en: str | None = None
    romaji: str | None = None
    genres: str | None = None
    profile_text: str | None = None
    memo: str | None = None
    birth_date: str | None = None
    debut_date: str | None = None
    height: int | None = None
    bust: int | None = None
    waist: int | None = None
    hip: int | None = None
    cup_size: str | None = None
    agency: str | None = None
    is_favorite: bool | None = None
    favorite_intensity: float | None = None
    user_score: float | None = None


class ActressMergeRequest(BaseModel):
    merge_id: int


class AliasCreateRequest(BaseModel):
    alias_name: str
    alias_type: str = "stage"
    is_primary: bool = False


# ── Folder watch ─────────────────────────────────────────────────────────────


class FolderBindingInboxItemSchema(BaseModel):
    product_code: str
    old_path: str = ""
    candidates: list[str] = []
    monitoring_paused: bool = False


class FolderBindingInboxResponse(BaseModel):
    revision: int
    items: list[FolderBindingInboxItemSchema]


class FolderBindingCandidatesRequest(BaseModel):
    product_code: str
    old_path: str = ""


class FolderBindingCandidatesResponse(BaseModel):
    candidates: list[str]


# ── Insight ──────────────────────────────────────────────────────────────────


class InsightOverviewResponse(BaseModel):
    stats: dict[str, Any] = {}
    top_actors: list[dict[str, Any]] = []
    top_genres: list[dict[str, Any]] = []
    top_makers: list[dict[str, Any]] = []
    recent_trend: dict[str, Any] = {}
    weekly_digest: dict[str, Any] = {}
    pipeline: dict[str, Any] = {}
    monthly_genre_trend: list[dict[str, Any]] = []
    monthly_additions: list[dict[str, Any]] = []
    distribution: dict[str, Any] = {}


class InsightTrendsResponse(BaseModel):
    watch_summary: dict[str, Any] = {}
    monthly_genre_trend: list[dict[str, Any]] = []
    recent_trend: dict[str, Any] = {}


class InsightRecommendResponse(BaseModel):
    today_recs: list[dict[str, Any]] = []
    next_watch: list[dict[str, Any]] = []
    hidden_gems: list[dict[str, Any]] = []
    favorite_actor_picks: list[dict[str, Any]] = []


class InsightCollectionResponse(BaseModel):
    distribution: dict[str, Any] = {}
    actor_collections: dict[str, Any] = {}
    pipeline: dict[str, Any] = {}
