"""The app as an installed copy runs it (`uv run prestcribe`): the API under /api, where the frontend asks for it, and the built
frontend (frontend/dist, from `npm --prefix frontend run build`) at /."""
from fastapi import FastAPI

from backend.api.main import app as api
from backend.common import ROOT

site = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
site.mount("/api", api)
site.frontend("/", directory=ROOT / "frontend" / "dist", fallback="index.html")
