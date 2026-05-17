# JAVSTORY 인사이트(InsightView) 기능 확장 기획

> **작성일**: 2026-05-17  
> **대상 파일**: `gui/InsightView.qml`, `javstory/analytics/` 모듈 전체  
> **목적**: 현재 취향 분석 대시보드를 "나만의 미디어 인텔리전스 센터"로 확장  

---

## 현재 구현 현황 (베이스라인)

`progress_report.md` 기준으로 현재 인사이트 뷰는 아래 모듈과 연동되어 있음:

| 모듈 | 경로 | 역할 |
|------|------|------|
| 취향 엔진 | `javstory/analytics/preference_engine.py` | 선호도 학습 |
| 라이브러리 통계 | `javstory/analytics/library_stats.py` | 수량/분포 통계 |
| 배치 워커 | `javstory/analytics/batch_worker.py` | 비동기 처리 |

현재는 **과거 데이터 기반 통계 시각화** 수준으로 추정됨. 아래는 이 베이스 위에 추가할 확장 기능들.

---

## 📊 확장 그룹 1: 심층 취향 프로파일링 (Taste DNA)

### 1-A. 취향 레이더 차트 (Taste Radar)

**개념**: 내 라이브러리를 6~8개 축으로 분해해서 레이더 차트로 시각화

```
분석 축 예시:
- 스토리 밀도 (씬 수 / 영상 길이)
- 독백형 vs 대화형 (자막 분석)
- 분위기 (ambient score: 밝음/어두움/자극적)
- 장르 편중도 (장르 HHI 지수)
- 배우 다양성 (신규 배우 비율)
- 출시 연도 분포 (신작 선호 vs 클래식 선호)
```

**구현 경로**:
- `library_stats.py`에 `compute_taste_vector(product_ids) -> dict` 추가
- `InsightView.qml`에 Canvas 기반 레이더 차트 위젯 추가
- 월별 스냅샷 저장으로 "취향 변화 타임라인" 가능

**연동 데이터**: 기존 씬 분석 결과(`scenes` 테이블), 자막 JSON, 장르 태그

---

### 1-B. 배우 친밀도 그래프 (Actor Affinity Map)

**개념**: 자주 보는 배우들을 노드로, 함께 출연한 작품 수를 엣지로 연결한 네트워크 그래프

```
시각화 예시:
배우 A ──(3편)── 배우 B
배우 A ──(1편)── 배우 C
배우 B ──(5편)── 배우 D  ← "핵심 클러스터"
```

**활용**:
- "배우 B를 좋아하면 배우 D도 좋아할 가능성 높음" → 추천 트리거
- 내가 한 번도 안 본 배우인데 내 선호 클러스터에 연결된 배우 발견

**구현 경로**:
- `preference_engine.py`에 `compute_actor_graph() -> networkx.Graph` 추가 (`networkx` 의존성 추가)
- QML에서는 Python 측이 노드/엣지 JSON을 내려주고, Canvas로 포스 레이아웃 렌더링
- 또는 간단하게 `D3.js` 기반 웹뷰 임베딩 (`QWebEngineView`)

---

### 1-C. 나의 취향 페르소나 카드 (Persona Card)

**개념**: AI(Ollama/Grok)가 내 라이브러리 통계를 분석해 자연어 취향 요약 생성

```
예시 출력:
┌─────────────────────────────────────────┐
│  🎭 당신의 취향 페르소나                   │
│  "스토리텔러형 감상자"                     │
│                                         │
│  대화 중심의 씬을 선호하며, 특정 배우에    │
│  강한 팬십을 보이는 타입입니다.            │
│  최근 3개월간 취향이 "밝은 분위기" 쪽으로  │
│  이동 중입니다.                           │
└─────────────────────────────────────────┘
```

**구현 경로**:
- `preference_engine.py`에서 통계 dict 추출 후 `ollama` API로 프롬프트
- 결과를 `data/cache/persona_card.json`에 캐시 (주 1회 갱신)
- `InsightView.qml`에 GlassCard 스타일로 표시

---

## 📈 확장 그룹 2: 시간축 분석 (Temporal Intelligence)

### 2-A. 감상 캘린더 히트맵 (Watch Calendar)

**개념**: GitHub 잔디처럼 날짜별 감상량을 히트맵으로 표시

```
5월
Mon  ░░░░▓▓░░░░▓▓▓░
Wed  ░░░▓▓▓▓░░░░░░░
Fri  ░▓▓▓░░░░░▓░░░░
            ↑
          집중 감상일
```

**구현 경로**:
- DB에 `watched_at` 타임스탬프 컬럼 필요 (현재 스키마에 없을 수 있음 → 마이그레이션)
- `library_stats.py`에 `get_watch_heatmap(year) -> dict[date, count]` 추가
- QML Canvas로 GitHub 잔디 스타일 렌더링

---

### 2-B. 취향 드리프트 타임라인 (Taste Drift)

**개념**: 분기/월별로 선호 장르·배우가 어떻게 변했는지 스택 바 차트

```
2025 Q1: ██████████ 장르A  ████ 장르B  ██ 장르C
2025 Q2: ████████ 장르A  ██████ 장르B  ████ 장르D
2025 Q3: ████ 장르A  ████████████ 장르B  ████ 장르E
                     ↑ 장르B로 취향 이동 중
```

**활용**: "나는 이 시기에 어떤 취향이었나" 자기 인식 + 추천 모델 개선

**구현 경로**:
- `preference_engine.py`에 `get_preference_timeline(granularity='month') -> list[dict]` 추가
- QML에 recharts 스타일 스택 바 위젯 (Canvas 직접 구현 or QWebEngineView + Chart.js)

---

### 2-C. 분석 공장 생산성 리포트 (Pipeline Report)

**개념**: 파이프라인이 얼마나 열심히 돌았는지 보여주는 운영 지표 대시보드

```
이번 달 처리 현황
─────────────────────────────
신규 수확:     23편  (+5 vs 지난달)
분석 완료:     19편
오류 복구:      4건
평균 처리시간: 18분/편
총 GPU 사용:  142시간
```

**구현 경로**:
- `error_recovery.py`, `watchdog` 로그에서 집계
- `javstory/analytics/pipeline_stats.py` 신규 모듈로 분리
- InsightView의 탭 중 하나로 추가

---

## 🎯 확장 그룹 3: 능동적 추천 엔진 (Active Recommendation)

### 3-A. "다음에 볼 작품" 스마트 추천 (Next Watch)

**개념**: 현재 분위기/시간대/최근 감상 패턴을 기반으로 즉각적 추천

```
[지금 바로 보기 추천]
┌────────────────────────────────────────┐
│  최근 사흘 동안 밝은 분위기 작품만 보셨네요. │
│  오늘은 조금 다른 분위기 어떨까요?          │
│                                         │
│  🎬 STAR-471  ★ 일치도 94%             │
│  🎬 OFJE-223  ★ 일치도 87%             │
└────────────────────────────────────────┘
```

**구현 경로**:
- `preference_engine.py`에 `get_recommendations(n=5, context='evening') -> list[Product]` 추가
- 이미 있는 `javstory/library/embeddings/` 벡터 스토어와 연동 (코사인 유사도 기반 필터링)
- 신규 배치: `preference_engine` → 임베딩 쿼리 → 결과 랭킹 → QML 카드 표시

---

### 3-B. 미발굴 작품 발견 (Hidden Gems)

**개념**: 라이브러리에 있지만 한 번도 안 본, 또는 낮게 평가했지만 취향과 실제로 잘 맞는 작품 발굴

```
[당신이 놓친 보석들]
MIMK-267  — 라이브러리에 6개월 있었지만 미감상
            취향 일치도 ★★★★☆ (장르/배우 기준)
```

**구현 경로**:
- `library_stats.py`에 `get_unwatched_gems() -> list[Product]` 추가
- 평가 점수(`rating`)와 취향 벡터 유사도의 괴리가 큰 항목 탐지

---

### 3-C. 배우별 작품 완독률 (Actor Completion Rate)

**개념**: 특정 배우의 작품을 얼마나 완료했는지 시각화 + 미감상 알림

```
배우별 컬렉션 완성도
────────────────────────────
배우 A  [████████░░] 8/10편 완료
배우 B  [████░░░░░░] 4/9편  완료  ← 5편 미감상
배우 C  [██████████] 전체 완료 🏆
```

**구현 경로**:
- `library_stats.py`에 `get_actor_collection_stats() -> dict[actor, CompletionStats]` 추가
- DB에 배우-작품 관계가 있어야 함 (DB v2 스키마 마이그레이션과 연동)

---

## 🔔 확장 그룹 4: 알림 및 자동화 (Smart Alerts)

### 4-A. 취향 기반 신작 알림 (New Release Alert)

**개념**: Harvest가 새 작품을 수집할 때, 취향 벡터와 비교해 "이건 마음에 드실 것 같습니다" 즉시 알림

```
[대시보드 토스트 알림]
🔔 취향 일치 신작 발견
   STAR-999 — 일치도 91%
   [바로 분석 큐 추가]  [나중에]
```

**구현 경로**:
- `Harvest/coordinator.py`의 수집 완료 훅에 `preference_engine.score(product)` 호출 추가
- 임계값(예: 85%) 초과 시 `ToastNotification` QML 컴포넌트 발동
- 알림 임계값은 Settings 뷰에서 조절 가능

---

### 4-B. 주간 취향 리포트 (Weekly Digest)

**개념**: 매주 월요일 앱 실행 시 지난 주 감상 요약 자동 생성

```
[지난 주 리포트 — 2026년 5월 2주차]
이번 주 7편 감상 (평균보다 +2편)
가장 많이 본 배우: 배우 A (3편)
새로 발견한 취향: "야외 씬" 선호 감지
추천 다음 작품: STAR-471
```

**구현 경로**:
- `javstory/analytics/weekly_digest.py` 신규 모듈
- `batch_worker.py`에 스케줄 태스크로 등록 (매주 실행)
- 결과를 `data/cache/weekly_digest.json`에 저장 후 InsightView 상단 배너로 표시

---

## 🗂️ 구현 로드맵 및 우선순위

| 우선순위 | 기능 | 난이도 | 기존 코드 활용도 | 예상 작업일 |
|----------|------|--------|-----------------|------------|
| 🔴 높음 | 1-A. 취향 레이더 차트 | 중 | 높음 (library_stats 확장) | 2~3일 |
| 🔴 높음 | 3-A. 스마트 추천 Next Watch | 중 | 높음 (embeddings 이미 구현) | 2~3일 |
| 🔴 높음 | 4-A. 신작 알림 | 중 | 높음 (Harvest 훅 + Toast 이미 있음) | 1~2일 |
| 🟠 중간 | 2-A. 감상 캘린더 히트맵 | 소 | 중 (DB 컬럼 추가 필요) | 1~2일 |
| 🟠 중간 | 1-C. 취향 페르소나 카드 | 소 | 높음 (Ollama 이미 연동) | 1일 |
| 🟠 중간 | 2-C. 파이프라인 리포트 | 소 | 높음 (로그 집계) | 1~2일 |
| 🟡 낮음 | 1-B. 배우 친밀도 그래프 | 대 | 중 (networkx 신규) | 3~5일 |
| 🟡 낮음 | 2-B. 취향 드리프트 타임라인 | 중 | 중 | 2~3일 |
| 🟡 낮음 | 3-B. Hidden Gems | 소 | 중 | 1~2일 |
| 🟡 낮음 | 3-C. 배우 완독률 | 중 | 낮음 (DB v2 필요) | DB v2 이후 |
| 🟢 나중 | 4-B. 주간 다이제스트 | 중 | 중 | 2~3일 |

---

## 📁 신규/수정 파일 목록

### 신규 생성
```
javstory/analytics/
├── taste_vector.py          # 취향 벡터 계산 (레이더, 드리프트용)
├── actor_graph.py           # 배우 친밀도 그래프
├── persona_card.py          # AI 페르소나 카드 생성
├── weekly_digest.py         # 주간 리포트
└── pipeline_stats.py        # 파이프라인 운영 지표

gui/
└── components/
    ├── RadarChartWidget.qml  # 레이더 차트
    ├── HeatmapWidget.qml     # 캘린더 히트맵
    └── PersonaCard.qml       # 페르소나 카드
```

### 수정 필요
```
javstory/analytics/preference_engine.py  # 추천/유사도 함수 추가
javstory/analytics/library_stats.py      # 통계 함수 확장
javstory/Harvest/coordinator.py          # 신작 알림 훅 추가
gui/InsightView.qml                      # 새 위젯들 레이아웃 통합
```

### DB 마이그레이션 필요
```sql
-- watched_at 컬럼 (히트맵용)
ALTER TABLE jav_metadata ADD COLUMN watched_at TIMESTAMP;

-- 평가 점수 (Hidden Gems용)
ALTER TABLE jav_metadata ADD COLUMN user_rating REAL DEFAULT NULL;
```

---

## 💬 커서(Cursor)에게 전달할 지시사항

아래를 커서에게 그대로 붙여넣어 사용:

```
InsightView 기능 확장을 진행해줘. 우선순위 높음 3개를 먼저 구현해:

1. [1-A] javstory/analytics/library_stats.py에 compute_taste_vector() 함수 추가.
   배우 다양성, 장르 편중도, 스토리 밀도, 출시연도 분포 등 6개 축을 반환하는 dict 형태.
   그리고 gui/components/RadarChartWidget.qml을 신규 생성해서
   InsightView.qml에 통합해줘.

2. [3-A] javstory/analytics/preference_engine.py에 get_recommendations(n=5) 함수 추가.
   javstory/library/embeddings/ 의 벡터 스토어를 활용해서
   현재 미감상 작품 중 코사인 유사도 상위 n개를 반환.
   InsightView.qml에 "다음에 볼 작품" 카드 섹션 추가.

3. [4-A] javstory/Harvest/coordinator.py의 수집 완료 훅에
   preference_engine.score(product) 호출을 추가하고,
   임계값(기본 0.85) 초과 시 QML의 ToastNotification을 발동하는
   시그널을 Python 측에서 emit하도록 연결해줘.
   임계값은 Settings에서 조절 가능하게 설정 항목 추가.

기존 GlassCard, ActionButton 등 공통 컴포넌트 스타일을 일관되게 유지해줘.
```
