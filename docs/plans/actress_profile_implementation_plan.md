# JAVSTORY 배우 프로필 — 수정 및 구현 계획

작성일: 2026-06-20  
분석 기준: 요구사항 `actress_profile_db_expansion.md` 대비 현재 구현 상태

---

## 현재 상태 요약

| 레이어 | 완성도 | 비고 |
|--------|--------|------|
| DB 스키마 / 마이그레이션 | 90% | `created_at/updated_at` 누락, NOT NULL 제약 없음 |
| Python 백엔드 (ActressModel) | 70% | 슬롯 구조는 완성, 작품 조회 로직 오류 |
| QML 컴포넌트 뼈대 | 75% | 컴포넌트 파일 모두 존재, 인터랙션 미연결 |
| 실제 동작 UI | 20% | 대부분 `toastMessage("구현 예정")` placeholder |

---

## Phase 1 — 긴급 버그 수정 (현재 동작 안 함)

### BUG-01: QML ↔ Python `currentProfile` 키 이름 불일치
**영향**: 배우 상세 화면 전체가 빈 값으로 표시됨

원인: Python `loadProfile()`에서 `name_ko`, `name_ja`, `is_favorite`, `user_score` 키로 저장하지만,  
QML `ActressView.qml`에서 `currentProfile.nameKo`, `currentProfile.isFavorite` 등 camelCase로 접근.

**수정 위치**: `gui/qml/views/ActressView.qml`

```
currentProfile.nameKo        →  currentProfile.name_ko
currentProfile.nameJa        →  currentProfile.name_ja
currentProfile.isFavorite    →  currentProfile.is_favorite
currentProfile.userScore     →  currentProfile.user_score
currentProfile.birth_date    →  그대로 (이미 snake_case)
```

### BUG-02: `getLibraryWorks` 검색 로직 오류
**영향**: 배우 클릭 시 연관 작품이 항상 0건

원인: `actors_ko.ilike(f"%{actress_id}%")` — 정수 actress_id를 배우 이름 텍스트 컬럼에서 검색.

**수정 위치**: `gui/models/actress_model.py` → `getLibraryWorks()`

```python
# 수정 후: actress의 이름으로 actors_ko / actors_ja 검색
row = session.query(Actress).filter_by(id=actress_id).first()
name = row.name_ko or row.name_ja or row.japanese or ""
rows = session.query(JAVMetadata).filter(
    JAVMetadata.actors_ko.ilike(f"%{name}%") |
    JAVMetadata.actors_ja.ilike(f"%{name}%") |
    JAVMetadata.actors.ilike(f"%{name}%")
).limit(50).all()
```

### BUG-03: `Actress` 모델 `updated_at` 컬럼 누락
**영향**: `updateProfile()`에서 `actress.updated_at = datetime.now()` 호출 시 AttributeError 발생 가능

**수정 위치**: `javstory/harvest/database.py` → `Actress` 클래스  
Alembic 마이그레이션에 `created_at`, `updated_at` 컬럼 추가 필요.

### BUG-04: 별명 삭제 슬롯 없음
**영향**: AliasManager의 "×" 버튼 클릭 시 `console.log`만 출력, DB 미반영

**수정 위치**: `gui/models/actress_model.py` — `removeAlias(alias_id)` 슬롯 추가  
`gui/qml/views/ActressView.qml` — `onRemoveAlias` 핸들러 연결

### BUG-05: `addActress()`에서 `genres` 필드 누전달
**영향**: 새 배우 추가 시 장르 정보가 저장되지 않음

**수정 위치**: `gui/models/actress_model.py` → `addActress()`

```python
# 추가
genres=data.get("genres", "").strip(),
```

---

## Phase 2 — 핵심 UI 인터랙션 연결

### FEAT-01: 즐겨찾기 Switch DB 반영
**위치**: `gui/qml/views/ActressView.qml` — 즐겨찾기 Switch `onCheckedChanged`

```qml
onCheckedChanged: {
    if (actressModel && actressModel.currentProfile.id) {
        actressModel.updateProfile(
            actressModel.currentProfile.id,
            { "is_favorite": checked }
        )
    }
}
```

### FEAT-02: 관심도 Slider 저장
**위치**: `gui/qml/views/ActressView.qml` — Slider `onMoved`

디바운스(500ms Timer)를 걸어 드래그 중 과도한 DB 호출 방지.

```qml
Timer {
    id: intensityTimer
    interval: 500
    onTriggered: {
        actressModel.updateProfile(
            actressModel.currentProfile.id,
            { "favorite_intensity": intensitySlider.value }
        )
    }
}
// Slider onMoved: intensityTimer.restart()
```

### FEAT-03: Memo 자동 저장 (디바운스)
**위치**: `gui/qml/views/ActressView.qml` — TextArea `onTextChanged`

Slider와 동일한 패턴. `Timer { interval: 1000 }` 로 1초 뒤 저장.

### FEAT-04: 사진 추가 — FileDialog 연결
**위치**: `gui/qml/views/ActressView.qml`  
`ActressGallery.qml`의 `onAddImageRequested` 핸들러에서 `FileDialog` 열기.

```qml
FileDialog {
    id: imageFileDialog
    title: "사진 선택"
    nameFilters: ["이미지 파일 (*.jpg *.jpeg *.png *.webp)"]
    onAccepted: {
        var localPath = selectedFile.toString().replace("file:///", "")
        actressModel.addImage(currentActressId, localPath, false)
    }
}
```

### FEAT-05: DropArea 실제 처리
**위치**: `gui/qml/components/ActressGallery.qml` — `DropArea.onDropped`

```qml
onDropped: {
    for (var i = 0; i < drop.urls.length; i++) {
        var localPath = drop.urls[i].toString().replace("file:///", "")
        // signal로 상위 ActressView에 전달
        root.imagesDropped([localPath])
    }
}
```

`ActressView`에서 `onImagesDropped`를 받아 `actressModel.addImage()` 루프 호출.

### FEAT-06: `addImage()`에서 is_profile=true 시 `profile_image_url` DB 업데이트
**위치**: `javstory/utils/actress_profile.py` → `save_actress_image()`  
`gui/models/actress_model.py` → `addImage()`

이미지 저장 성공 후, `is_profile=True`면 `Actress.profile_image_url`도 갱신:

```python
if is_profile and path:
    with get_db_session_ctx() as session:
        actress = session.query(Actress).filter_by(id=actress_id).first()
        if actress:
            actress.profile_image_url = str(path.relative_to(DATA_ROOT))
            session.commit()
```

---

## Phase 3 — 미구현 UI 컴포넌트

### FEAT-07: 새 배우 추가 Dialog
**위치**: `gui/qml/views/ActressView.qml` 내 인라인 Dialog 또는 별도 `AddActressDialog.qml`

필드 구성:
- Row 1: 이름 (JA), 이름 (KO), 이름 (EN)
- Row 2: 생년월일, 키, 컵사이즈
- Row 3: 버스트, 허리, 힙
- Row 4: 데뷔일, 소속사
- Row 5: 장르 (쉼표 구분 입력)
- Row 6: 프로필 소개 (profile_text) — TextArea
- Row 7: 메모 — TextArea
- 하단: 취소 / 저장 버튼

저장 시 `actressModel.addActress(formData)` 호출.

### FEAT-08: 편집 모드 (인플레이스)
**위치**: `gui/qml/views/ActressView.qml` 우측 상세 패널

접근 방식: 상세 패널에 `isEditMode: bool` 상태 변수를 두고,  
"편집" 버튼 → `isEditMode = true` → 각 `Text` → `TextField`로 전환.  
"저장" 버튼 → `actressModel.updateProfile(id, changedFields)` 호출 → `isEditMode = false`.

필드별 전환:
```qml
// 조회 모드
Text { visible: !isEditMode; text: currentProfile.name_ko }
// 편집 모드
TextField { visible: isEditMode; text: currentProfile.name_ko }
```

### FEAT-09: 검색 필터 연결
**위치**: `gui/qml/views/ActressView.qml` — SearchBar `onTextChanged`

```qml
onTextChanged: {
    if (root.actressModel) {
        var results = root.actressModel.searchActresses(text)
        root.actressModel.listModel.set_actresses(results)  // → Python slot 필요
    }
}
```

`ActressModel`에 QML에서 호출 가능한 `filterList(query: str)` 슬롯 추가.  
`filterList`는 `searchActresses`와 동일한 로직이지만 `_list_model`을 직접 업데이트.

### FEAT-10: 정렬 기능
**위치**: `gui/qml/views/ActressView.qml` — 헤더에 ComboBox 추가

정렬 옵션: 이름순 (가나다) / 즐겨찾기 우선 / 점수 높은순 / 최근 추가순

`ActressModel.reload(sort: str)` 슬롯에 `sort` 파라미터 추가:
```python
ORDER_MAP = {
    "name": Actress.name_ko.asc().nullslast(),
    "favorite": Actress.is_favorite.desc(),
    "score": Actress.user_score.desc().nullslast(),
    "recent": Actress.id.desc(),
}
```

### FEAT-11: 시청 정보 섹션 UI 추가
**위치**: `gui/qml/views/ActressView.qml` 상세 패널 — "선호도" GlassCard 아래

```qml
GlassCard {
    title: "시청 기록"
    GridLayout {
        columns: 2
        Text { text: "시청 횟수" }
        Text { text: currentProfile.watch_count + "회" }
        Text { text: "강반응 횟수" }
        Text { text: currentProfile.strong_reaction_count + "회" }
        Text { text: "마지막 시청" }
        Text { text: currentProfile.last_watched || "-" }
        Text { text: "시청 점수" }
        Text { text: currentProfile.user_score.toFixed(1) }
    }
}
```

### FEAT-12: 작품 수 / 작품 리스트 UI
**위치**: `gui/qml/views/ActressView.qml` 상세 패널 — 시청 정보 카드 아래

BUG-02 수정 후 `getLibraryWorks(id)` 결과를 표시:

```qml
GlassCard {
    title: "라이브러리 작품 (" + worksModel.count + ")"
    
    ListView {
        model: worksModel  // ListModel
        delegate: RowLayout {
            Text { text: model.product_code }
            Text { text: model.title_ko; elide: Text.ElideRight }
            MouseArea {
                onClicked: {
                    // LibraryModel.navigateToProduct(product_code) 호출
                }
            }
        }
    }
}
```

`ActressView`에서 `currentProfileChanged` 시 `actressModel.getLibraryWorks(id)` 호출 후 `ListModel` 채우기.

### FEAT-13: 장르 Chip → Library 필터 연동
**위치**: `gui/qml/views/ActressView.qml` — 장르 Chip `MouseArea.onClicked`

`main.qml`에 `filterLibraryByGenre(genre: string)` 함수 추가.  
`LibraryModel`에 장르 필터 파라미터 전달 후 Library 탭으로 이동:

```qml
onClicked: {
    var genre = modelData.trim()
    LibraryModel.setGenreFilter(genre)
    // main.qml의 StackLayout index를 Library 탭으로 전환
    mainWindow.switchToLibrary()
}
```

---

## Phase 4 — DB 스키마 보완 (Alembic 마이그레이션)

### DB-01: `Actress.created_at / updated_at` 추가
새 마이그레이션 파일: `versions/d5a638a6528e_add_actress_timestamps.py`

```python
op.add_column('actresses', sa.Column('created_at', sa.DateTime(),
    server_default=sa.text('(CURRENT_TIMESTAMP)')))
op.add_column('actresses', sa.Column('updated_at', sa.DateTime(),
    server_default=sa.text('(CURRENT_TIMESTAMP)')))
```

`database.py` `Actress` 모델에도 컬럼 추가:
```python
created_at = Column(DateTime, default=datetime.datetime.now)
updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
```

### DB-02: `profile_image_url` String(500) → Text
현재 500자 제한 → 긴 경로 잘릴 수 있음. 마이그레이션으로 타입 변경.

---

## Phase 5 — 연동 준비 (Persona Chat / 추천 시스템)

### FEAT-14: Persona Chat에서 배우 DB 참조
**위치**: `javstory/utils/actress_profile.py`에 `get_actress_context(actress_id)` 함수 추가

```python
def get_actress_context(actress_id: int) -> dict:
    """Persona Chat 프롬프트용 배우 컨텍스트 반환."""
    with get_db_session_ctx() as session:
        row = session.query(Actress).filter_by(id=actress_id).first()
        if not row:
            return {}
        return {
            "name": row.name_ko or row.name_ja,
            "genres": row.genres,
            "memo": row.memo,
            "profile_text": row.profile_text,
            "user_score": row.user_score,
        }
```

추후 `PersonaChatModel`에서 `get_actress_context()` 호출하여 프롬프트에 주입.

### FEAT-15: 추천 시스템에서 배우 선호도 참조
`Actress.is_favorite`, `Actress.favorite_intensity`, `Actress.genres`를  
`UserPreference` 테이블 보완 데이터로 활용하는 훅 포인트 준비.  
(실제 추천 로직은 별도 태스크)

---

## ToDo 체크리스트

### Phase 1 — 긴급 버그 수정

- [ ] **BUG-01** `ActressView.qml` — `currentProfile` 접근 키 전체 수정 (nameKo→name_ko 등)
- [ ] **BUG-02** `actress_model.py` — `getLibraryWorks()` 검색 로직 수정 (id→name 기반)
- [ ] **BUG-03** `database.py` — `Actress` 모델에 `created_at`, `updated_at` 컬럼 추가
- [ ] **BUG-03** Alembic 마이그레이션 — actresses 테이블에 타임스탬프 컬럼 추가
- [ ] **BUG-04** `actress_model.py` — `removeAlias(alias_id)` 슬롯 추가
- [ ] **BUG-04** `ActressView.qml` — `onRemoveAlias` 핸들러 실제 슬롯 호출 연결
- [ ] **BUG-05** `actress_model.py` — `addActress()`에 `genres` 필드 전달 추가

### Phase 2 — 핵심 인터랙션 연결

- [ ] **FEAT-01** `ActressView.qml` — 즐겨찾기 Switch `onCheckedChanged` → `updateProfile` 연결
- [ ] **FEAT-02** `ActressView.qml` — 관심도 Slider에 디바운스 Timer(500ms) + `updateProfile` 연결
- [ ] **FEAT-03** `ActressView.qml` — Memo TextArea 디바운스 Timer(1000ms) + `updateProfile` 연결
- [ ] **FEAT-04** `ActressView.qml` — `FileDialog` 추가, `onAddImageRequested` 핸들러 연결
- [ ] **FEAT-05** `ActressGallery.qml` — `DropArea.onDropped`에서 `imagesDropped` 시그널 emit
- [ ] **FEAT-05** `ActressView.qml` — `onImagesDropped` 핸들러에서 `actressModel.addImage()` 루프
- [ ] **FEAT-06** `actress_profile.py` + `actress_model.py` — `is_profile=True` 저장 시 `profile_image_url` 자동 갱신

### Phase 3 — 미구현 UI

- [ ] **FEAT-07** `AddActressDialog.qml` 신규 파일 생성 (전체 필드 입력 폼)
- [ ] **FEAT-07** `ActressView.qml` — "새 배우 추가" 버튼 → Dialog open 연결
- [ ] **FEAT-07** `qmldir` — `AddActressDialog 1.0 AddActressDialog.qml` 등록
- [ ] **FEAT-08** `ActressView.qml` — `isEditMode` 상태 변수 추가
- [ ] **FEAT-08** `ActressView.qml` — 상세 패널 각 필드 `Text` ↔ `TextField` 조건부 전환 구현
- [ ] **FEAT-08** `ActressView.qml` — "저장" 버튼 → `updateProfile(id, changedFields)` 연결
- [ ] **FEAT-09** `actress_model.py` — `filterList(query)` 슬롯 추가 (list_model 직접 업데이트)
- [ ] **FEAT-09** `ActressView.qml` — SearchBar `onTextChanged` → `filterList()` 연결
- [ ] **FEAT-10** `ActressView.qml` — 정렬 ComboBox 추가
- [ ] **FEAT-10** `actress_model.py` — `reload(sort)` 파라미터 추가 + ORDER_MAP 구현
- [ ] **FEAT-11** `ActressView.qml` — "시청 기록" GlassCard 섹션 추가
- [ ] **FEAT-12** `ActressView.qml` — "라이브러리 작품" GlassCard + ListView 추가
- [ ] **FEAT-12** `ActressView.qml` — 프로필 로드 시 `getLibraryWorks()` 호출 → 작품 ListModel 채우기
- [ ] **FEAT-13** `main.qml` — `filterLibraryByGenre(genre)` 함수 + Library 탭 전환 로직 추가
- [ ] **FEAT-13** `ActressView.qml` — 장르 Chip 클릭 → `filterLibraryByGenre` 호출

### Phase 4 — DB 보완

- [ ] **DB-01** `database.py` — `Actress` 모델 `created_at`, `updated_at` 컬럼 추가
- [ ] **DB-01** 새 Alembic 마이그레이션 파일 작성 및 `user_version` 13으로 업데이트
- [ ] **DB-02** `database.py` — `Actress.profile_image_url` `String(500)` → `Text` 변경

### Phase 5 — 연동 준비

- [ ] **FEAT-14** `actress_profile.py` — `get_actress_context(actress_id)` 유틸 함수 추가
- [ ] **FEAT-15** 추천 시스템 훅 포인트 문서화 (실제 구현은 별도 태스크)

---

## 구현 순서 권장

```
Phase 1 (버그 수정) → Phase 2 (인터랙션 연결) → Phase 4 (DB 보완)
         ↓
Phase 3-A: 편집 모드(FEAT-08) + 새 배우 추가(FEAT-07)
         ↓
Phase 3-B: 검색(FEAT-09) + 정렬(FEAT-10) + 시청/작품 UI(FEAT-11, 12)
         ↓
Phase 3-C: 장르 필터 연동(FEAT-13)
         ↓
Phase 5 (연동 준비)
```

Phase 1과 Phase 2는 기존 UI가 제대로 동작하기 위한 전제 조건이므로 가장 먼저 처리.  
Phase 3-A는 수동 입력 방식의 핵심 기능.  
Phase 3-B/C는 편의 기능.

---

## 파일별 수정 대상 정리

| 파일 | 작업 | Phase |
|------|------|-------|
| `gui/qml/views/ActressView.qml` | BUG-01, FEAT-01~05, FEAT-08~13 | 1~3 |
| `gui/models/actress_model.py` | BUG-02, BUG-04, BUG-05, FEAT-06, FEAT-09, FEAT-10, FEAT-12, FEAT-14 | 1~5 |
| `gui/qml/components/ActressGallery.qml` | FEAT-05 DropArea 실제 처리 | 2 |
| `javstory/harvest/database.py` | BUG-03, DB-01, DB-02 | 1, 4 |
| `javstory/utils/actress_profile.py` | FEAT-06, FEAT-14 | 2, 5 |
| `gui/qml/components/AddActressDialog.qml` | FEAT-07 신규 생성 | 3 |
| `gui/qml/components/qmldir` | FEAT-07 등록 | 3 |
| `gui/qml/main.qml` | FEAT-13 장르 필터 함수 | 3 |
| Alembic 마이그레이션 (신규) | DB-01 타임스탬프 컬럼 | 4 |
