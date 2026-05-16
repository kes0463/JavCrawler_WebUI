"""JAVSTORY FastAPI — Library + Harvest (non-production, frozen).

운영 UI는 main.py + QML. See docs/adr/0001-ui-stack-qml-only.md.
"""
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Electron / localhost:5173
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(harvest.router, prefix="/api/harvest", tags=["harvest"])


@app.get("/health")
def health():
    return {"status": "ok"}
