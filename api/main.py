"""JAVSTORY FastAPI — Library + Harvest (non-production, frozen).

운영 UI는 main.py + QML. See docs/adr/0001-ui-stack-qml-only.md.
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (javstory 패키지 임포트용)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import library, harvest

app = FastAPI(title="JAVSTORY API", version="1.0.0")

# 허용 origin: 개발(Vite) + 프로덕션 Electron(file:// → Origin: null)
# 추가 도메인이 필요할 경우 JAVSTORY_CORS_ORIGINS 환경변수에 쉼표 구분으로 지정
_cors_env = os.environ.get("JAVSTORY_CORS_ORIGINS", "").strip()
_CORS_ORIGINS: list[str] = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else [
        "http://localhost:5173",   # Vite 개발 서버
        "http://127.0.0.1:5173",   # Vite 개발 서버 (IP 직접 접근)
        "null",                    # Electron 프로덕션 (file:// 렌더러)
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(harvest.router, prefix="/api/harvest", tags=["harvest"])


@app.get("/health")
def health():
    return {"status": "ok"}
