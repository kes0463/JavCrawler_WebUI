# ADR 0001: 운영 UI — PySide6 + QML 단일 스택

- **상태**: Accepted
- **날짜**: 2026-05-16
- **검토 예정**: 2026-11-16 ~ 2027-05-16 (동결 6~12개월 후 삭제 여부)

## 맥락

JAVSTORY에는 UI 진입점이 두 갈래 존재한다.

| 스택 | 경로 | 역할 |
|------|------|------|
| 운영 | `main.py` → `gui/qml/`, `gui/models/` | Windows 데스크톱 앱 (`start.bat`) |
| 실험 | `frontend/` (React + Electron), `api/` (FastAPI) | 별도 빌드·HTTP 연동 프로토타입 |

운영 앱은 플레이어, STT, L4 `library_state`, 폴더 바인딩 등 전 기능이 QML·`javstory` 직접 호출에 묶여 있다.  
`frontend`/`api`는 라이브러리·Harvest 일부만 API로 노출하며 CI·배포 대상이 아니고, Processing 등은 목 데이터가 남아 있다.  
두 갈래를 병행하면 P3(DB v2 읽기)·신규 화면이 이중 구현·동작 불일치 위험이 있다.

## 결정

1. **운영 UI는 PySide6 + QML만 유지**한다. 신규 화면·버튼·상태·버그 수정은 `gui/qml/`, `gui/models/`(및 `javstory`)에만 추가한다.
2. **`frontend/`(React+Electron)와 `api/`(FastAPI)는 non-production으로 동결**한다.
   - 신규 기능 추가 금지
   - 버그 수정·의존성 업데이트·P3/P4 연동 대상에서 제외
   - 로컬 실험·UI 목업 참고용으로만 유지 가능
3. **삭제는 동결 시작일 기준 6~12개월 후 검토**한다 (본 ADR 검토 예정일). 삭제 전에 `git` 히스토리·별도 브랜치 보존 여부를 확인한다.

## 하지 않는 것

- QML 앱을 FastAPI 클라이언트로 전환
- `frontend`를 공식 진입점·`start.bat` 대체로 승격
- 동결 중 `api/routes`에 운영 기능을 맞추는 이중 유지보수

## 대안 (기각)

| 대안 | 기각 이유 |
|------|-----------|
| frontend+api를 본앱에 통합 | STT/GPU/로컬 파일·플레이어·L4 동기화를 HTTP+React로 재작성 비용 과대 |
| 두 스택 병행 개발 | 기능·테스트·문서 이중 부담, DB v2 읽기 경로 불일치 |

## 향후 통합을 재검토할 조건

- 원격/브라우저 UI가 **명시적 제품 요구**로 확정된 경우 → `javstory` 서비스 레이어 정리 후 **목적 제한 API**를 새로 설계 (동결된 `api/`를 그대로 확장하지 않음)

## 결과

- 단일 운영 스택으로 개발·리뷰·CI 범위가 `main.py` + QML에 집중된다.
- `frontend/`·`api/`는 참고용 아카이브; 혼동 방지를 위해 각 디렉터리 `README.md`에 동결 안내.

## 관련 문서

- [`docs/architecture/ENTRYPOINTS.md`](../architecture/ENTRYPOINTS.md)
- [`frontend/README.md`](../../frontend/README.md)
- [`api/README.md`](../../api/README.md)
