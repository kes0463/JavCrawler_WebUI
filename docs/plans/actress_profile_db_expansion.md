# JAVSTORY - Actress Profile DB Expansion Plan

**Version**: v1.0 (2026-06-20)
**Status**: Planning Complete → Ready for Implementation
**Related**: [DB_V2_DESIGN.md](../DB_V2_DESIGN.md), [ALEMBIC_MILESTONE.md](../ALEMBIC_MILESTONE.md), AVDBS actress page reference

## Purpose
기존 `jav_database.db`의 `actresses` 테이블을 확장하여 **배우 프로필**을 **수동 입력** 중심으로 풍부하게 관리.
AVDBS 배우 페이지 스타일을 참고한 **시각적·정보 중심 UI** 구현.
Persona Chat, 추천 시스템, 검색에서 DB를 적극 참조할 수 있도록 함.

## 1. DB Schema (New/Extended Tables)

### 1.1 `actresses` (기존 테이블 확장)
```sql
actress_id          INTEGER PRIMARY KEY AUTOINCREMENT
name_ja             TEXT NOT NULL
name_ko             TEXT NOT NULL                  -- 폴더명 생성 기준 (sanitized)
name_en             TEXT
profile_image_url   TEXT
genres              TEXT                             -- comma separated or JSON
user_score          REAL CHECK (user_score BETWEEN 0 AND 10)
profile_text        TEXT
birth_date          DATE
height              INTEGER                          -- cm
bust, waist, hip    INTEGER
cup_size            TEXT
debut_date          DATE
agency              TEXT
is_favorite         BOOLEAN DEFAULT 0
favorite_intensity  REAL CHECK (favorite_intensity BETWEEN 0 AND 10)
strong_reaction_count INTEGER DEFAULT 0
watch_count         INTEGER DEFAULT 0
last_watched        DATE
memo                TEXT
created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
```

**Notes**: 기존 `Actress` 모델(`japanese`, `korean`, `romaji`, `translation_note` 등)과 **호환** 유지. `name_ja` → `japanese` mapping.

### 1.2 `actress_images` (사진 갤러리)
```sql
image_id     INTEGER PRIMARY KEY
actress_id   INTEGER REFERENCES actresses(actress_id) ON DELETE CASCADE
image_url    TEXT NOT NULL
is_profile   BOOLEAN DEFAULT 0
sort_order   INTEGER DEFAULT 0
caption      TEXT
added_at     DATETIME DEFAULT CURRENT_TIMESTAMP
```

### 1.3 `actress_aliases` (별명 관리 - 핵심)
```sql
alias_id     INTEGER PRIMARY KEY
actress_id   INTEGER REFERENCES actresses(actress_id) ON DELETE CASCADE
alias_name   TEXT NOT NULL
alias_type   TEXT CHECK (alias_type IN ('stage', 'old', 'korean', 'english', 'other'))
is_primary   BOOLEAN DEFAULT 0
created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
```

**인덱스**:
- `idx_actresses_name_ko`, `idx_actress_aliases_name`, `idx_actress_images_actress_id`

## 2. File Storage Rules
- Root: `data/actress/`
- Per actress: `data/actress/{sanitized_name_ko}/`
  - `profile/` → 대표 사진 (1개 권장, `is_profile=true`)
  - `gallery/` → 추가 사진들 (sort_order로 정렬)
- **Sanitization**: `name_ko` → lowercase, 공백→`_`, 특수문자(`\/:*?"<>|`) 제거, 최대 50자.
- 이미지 저장 시 자동 resize (profile: 800x1200, gallery: 1200px max).

## 3. UI Requirements (AVDBS Style + GlassCard Dark Theme)
- **Main View** (`ActressView.qml`): 리스트(검색+필터) + 상세 Split View
- **Detail Layout**:
  - **Left (40%)**: Large profile photo + Horizontal/Vertical Gallery (thumbnails, click to enlarge, drag-drop add)
  - **Right (60%)**: 
    - Info Card (GlassCard): Basic specs (height, BWH, cup, birth, debut, agency), Genres as **Chips** (click → library genre filter)
    - Library Stats: "라이브러리 내 작품 수" + linked product list
    - Favorite Controls: Heart toggle + Intensity Slider (0-10)
    - **Aliases Section**: List + Add/Edit/Delete (type selector, primary flag)
    - Wide **Memo** textarea (rich text support if possible)
- **Style**: Existing `GlassCard`, `Theme.qml` (neon accents, dark glassmorphism), AVDBS-like clean photo-centric layout.

**Components to create**:
- `ActressProfileCard.qml`
- `ActressGallery.qml` (drag & drop support)
- `AliasManager.qml` (chips + form)
- `ActressListView.qml`

## 4. Core Features

### Actress Profile Tab & CRUD Flow (신규 요구사항)
- **배우 프로필 탭** (`ActressView.qml`): DB에 저장된 **배우 프로필 카드**들이 그리드 형태로 표시.
  - 카드 내용: 대표 사진, 이름 (ko/ja), user_score (별점), genres 주요 태그, favorite badge.
- **카드 클릭**: 상세 화면 (Split View 또는 Modal) 열림.
  - 좌측: Large profile photo + Gallery (drag & drop 지원).
  - 우측: Info (specs, BWH, birth, debut, agency), Genres **Chip** (입력/편집 지원, 클릭 시 Library filter), Library 작품 수 + 링크 리스트, Favorite toggle + Intensity slider, **Alias Manager**, 넓은 **Memo** 영역.
- **편집 모드**: "편집" 버튼 클릭 시 모든 필드 editable. 수정 후 "저장" 버튼으로 DB 즉시 연동 (`updated_at` 자동 갱신).
- **새 배우 추가**: 상단 **"새 배우 추가"** 버튼 → 빈 입력 폼 (name_ja/ko/en 필수, 나머지 선택). 저장 시 DB insert + folder 생성.
- **사진 추가**: 대표 사진 + 갤러리 (is_profile flag, sort_order 지원). 파일 선택 또는 Drag-and-Drop → 자동 folder 저장 (`data/actress/{name_ko}/profile/` or `/gallery/`).
- **모든 변경**: 실시간 DB 연동 (`actress_model` signals로 UI refresh).

### Additional Core Features
- **Genre Chips**: 입력/편집 지원 + 클릭 시 LibraryView genre filter.
- **Alias Handling**:
  - Search includes aliases (`actress_aliases.alias_name`).
  - "기존 배우와 연결" (merge/attach alias to existing profile).
  - Primary alias logic for display.
- **Stats Auto-update**: `watch_count`, `last_watched`, `strong_reaction_count` from `watch_history` / persona feedback.
- **Integration**:
  - Persona Chat / Recommendation: Query rich profile (`profile_text`, `user_score`, `memo`).
  - Library search: Alias-aware.
  - MasterSearchPopup extension for actress profiles.

### How to Add a New Actress Profile (Manual Input Flow)
1. **From LibraryDetail.qml** — Click an actress name in actors list → opens `ActressView.qml` with pre-filled `name_ja`/`name_ko`.
2. **From MasterSearchPopup** (existing "actress" mode) — "Add New Profile" button → opens form with basic fields.
3. **From Actress Profile Tab** — "새 배우 추가" button → full form (name_ja/ko/en, specs, profile_text, memo).
4. **Backend Flow** (`ActressModel.addActress(profile_data)`):
   - Sanitize `name_ko` → create folder `data/actress/{sanitized_name_ko}/profile/`
   - Insert into `actresses` table (new columns + existing `japanese` = name_ja mapping).
   - Optionally add initial `actress_aliases` (primary = true).
   - Return actress_id for immediate image upload.
5. **Photo Addition**: Drag-drop or "Add Photos" button → `save_actress_image()` → copies/resizes to folder and inserts into `actress_images`.
6. **Alias Management**: In detail view, "Add Alias" form (type selector: stage/old/korean) → inserts into `actress_aliases` with `is_primary` flag.

This flow ensures **수동 입력** is intuitive and integrates with existing actress picker logic.

## 5. Technical Implementation (Clean & Extensible)

### 5.1 Backend
- **Models** (`javstory/harvest/database.py`):
  - Extend `Actress` class with new columns.
  - Add `ActressProfile`, `ActressImage`, `ActressAlias` (or merge into one rich `Actress`).
  - Use Alembic for migration (new revision `0003_add_actress_profiles.py`).
- **Utils** (`javstory/utils/actress_profile.py`):
  - `sanitize_folder_name(name_ko)`
  - `save_actress_image(actress_id, file_path, is_profile=False)`
  - `get_actress_folder(name_ko)`
  - Alias resolver extension (`ActressResolver` update).
- **Model** (`gui/models/actress_model.py` - new):
  - `ActressModel(QObject)` with Q_PROPERTY, Slots (`addActress`, `updateProfile`, `addImage`, `manageAlias`, `searchActressesWithAliases` etc.).
  - DB session management via `get_db_session()`.
  - Signals for UI refresh (`actressListChanged`, `profileUpdated`).

### 5.2 Frontend (QML)
- Register `ActressModel` in `gui/app.py` / `main.qml`.
- Navigation: Add to `NavSidebar.qml`, use `NavigationContext`.
- Reuse: `GlassCard`, `RatingWidget`, `ActionButton`, `Theme` colors (neon blue/cyan accents).
- Drag-drop: Use `DropArea` + Python backend call.

### 5.3 Integration Points
- `gui/models/library_model.py`: Add actress profile lookup, genre filter from profile.
- `javstory/persona/*`: Inject `profile_text`, `memo`, `user_score` into prompts.
- `javstory/search/library_search.py`: Alias-aware full-text search.
- `gui/qml/views/LibraryDetail.qml`: Clickable actress names → open profile.

## 6. Style Guide & Code Quality
- **Clean Code**: Single responsibility, minimal new abstractions, reuse existing patterns (e.g. `LibraryModel` edit draft style).
- **No Gold Plating**: Implement exactly the spec. No extra config/flags unless required.
- **Security**: Safe file paths (no injection), image validation (size/type).
- **Dark Mode**: 100% consistent with existing `Theme.qml` (glass borders, neon accents).
- **Extensibility**: Easy to add VLM auto-tagging, auto-crawl later (via `profile_image_url`).

## 7. Implementation Roadmap (Phased)
1. **DB Migration** (Alembic revision + model update) — **First**
2. **Core Utils & ActressModel** (CRUD + image handling)
3. **QML Components** (Gallery, AliasManager, ProfileCard)
4. **Main ActressView.qml + Navigation**
5. **Integration** (Library, Persona, Search)
6. **Polish & Test** (drag-drop, alias search, stats sync)

**Estimated Effort**: 2-3 days (leveraging existing QML patterns and DB infrastructure).

## 8. Risks & Mitigations
- **Backward Compat**: Existing `Actress` queries unchanged (additive columns).
- **Migration**: Alembic `upgrade head` in boot sequence (see ALEMBIC_MILESTONE.md).
- **Data Loss**: Always backup `jav_database.db` before migration.
- **Folder Naming**: Collision handling (append number if duplicate `name_ko`).
- **Performance**: Index all name/alias columns; limit gallery queries.

## 9. Verification Criteria
- [ ] New tables created via Alembic.
- [ ] Can manually create actress with full profile + images + aliases.
- [ ] UI matches AVDBS visual density (photo left, clean info right).
- [ ] Alias search works in library/persona.
- [ ] Drag-drop photo saves to correct `data/actress/{name_ko}/` folder.
- [ ] Genres chips filter library correctly.
- [ ] `check-work` verification passes (build, UI, DB integrity).

**Next Step**: Approve this plan → Start with Alembic migration + model extension in `database.py`.

---
**Created by**: Grok (following user requirements exactly)
**File**: `docs/plans/actress_profile_db_expansion.md`
