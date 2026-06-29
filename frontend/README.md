# frontend/ — JAVSTORY WebUI

**ADR**: [0002 WebUI 2차 진입점](../docs/adr/0002-webui-secondary-entrypoint.md)

React + TypeScript + Tailwind + Vite 브라우저 UI입니다.

| 항목 | 내용 |
|------|------|
| 데스크톱 운영 UI | [`main.py`](../main.py) → PySide6 + QML |
| WebUI API | [`webapi/`](../webapi/) (FastAPI, port 8765) |
| 동결 레거시 | [`api/`](../api/) — **사용하지 않음** |

## 실행

```bat
start_web.bat
```

또는 터미널 2개:

```bat
uvicorn webapi.main:app --host 127.0.0.1 --port 8765 --reload
cd frontend && npm run dev
```

브라우저: http://localhost:5173

## MVP (실 API 연동)

- Dashboard — `/api/dashboard/*`
- Library — `/api/library/*`
- Harvest — `/api/harvest/*` + WebSocket
- **Actresses** — `/api/actresses/*` (목록·상세·편집·갤러리·별명·출연작·합치기)

### 배우 프로필 (Actresses)

데스크톱 QML `ActressView` / `ActressDetailPanel`과 동등한 기능:

- 목록 검색·정렬, 카드(장르·점수·즐겨찾기)
- 상세: 스펙 편집, 소개·메모, 관심도 슬라이더, 즐겨찾기
- 갤러리 업로드·대표 사진 지정·라이트박스
- 별명 CRUD, 배우 추가·합치기
- 출연작: 장르 필터, 정렬, 페이지네이션 → Library 상세 딥링크
- Library 상세 배우명 클릭 → Actress (미등록 시 추가 다이얼로그)

컴포넌트: `frontend/src/components/actress/`

### 수동 테스트 체크리스트

- [ ] `start_web.bat` 실행 후 http://localhost:5173/api/status 에서 `actress_count` > 0 확인
- [ ] Library 상세에서 배우 이름 클릭 → Actress 상세
- [ ] 미등록 배우 이름 클릭 → 추가 다이얼로그 prefill
- [ ] Actress 출연작 클릭 → Library 상세 패널 자동 오픈
- [ ] 갤러리 업로드 → 대표 사진 지정
- [ ] 별명 추가/삭제 → 목록 검색 반영
- [ ] 배우 합치기 후 작품수·별명 이전 확인

## 환경변수

| 변수 | 기본값 |
|------|--------|
| `VITE_API_BASE` | `http://127.0.0.1:8765` |

## 빌드

```bash
npm install
npm run build
```
