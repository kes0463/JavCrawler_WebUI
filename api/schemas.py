from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


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
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LibraryItemDetail(LibraryItem):
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


class LibraryListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[LibraryItem]


class LibraryStats(BaseModel):
    total: int
    with_metadata: int   # title_ko 존재
    with_folder: int     # folder_path 존재
    without_metadata: int


class HarvestStatus(str):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


class HarvestItem(BaseModel):
    id: str
    target: str
    product_code: Optional[str] = None
    status: str = "pending"
    progress: int = 0
    message: str = ""


class AddHarvestRequest(BaseModel):
    codes: list[str]  # ["STARS-001", "IPX-002", ...]


class HarvestQueueResponse(BaseModel):
    items: list[HarvestItem]
    running: bool
