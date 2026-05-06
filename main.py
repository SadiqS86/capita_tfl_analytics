"""ASGI entrypoint: FastAPI API + production SPA from ``frontend/dist`` (Databricks App)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_app import router as api_router

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="Capita TfL Analytics", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    if DIST.is_dir() and any(DIST.iterdir()):
        app.mount("/", StaticFiles(directory=str(DIST), html=True), name="spa")
    else:
        @app.get("/")
        def _dev_root() -> dict[str, str]:
            return {
                "message": "API only — build frontend (npm run build) or use Vite dev with proxy.",
                "health": "/api/health",
            }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
