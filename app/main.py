from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (регистрирует таблицы)
from .api import auth, events, public, venues
from .config import settings
from .db import Base, engine
from .domain.fields import PropsError

STATIC = Path(__file__).parent / "static"
(settings.media_dir / "public").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # для продакшена вместо этого — миграции Alembic
    yield


app = FastAPI(title="Venue Map API", version="0.1.0", lifespan=lifespan)
app.mount("/media", StaticFiles(directory=settings.media_dir / "public"), name="media")
for r in (auth.router, venues.router, events.router, public.router):
    app.include_router(r)


@app.exception_handler(PropsError)
async def props_error(_: Request, exc: PropsError):
    return JSONResponse(status_code=422, content={"detail": "ошибки в полях", "errors": exc.errors})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app")


@app.get("/app", include_in_schema=False)
def editor_page():
    return FileResponse(STATIC / "editor.html")


@app.get("/v/{slug}", include_in_schema=False)
def viewer_page(slug: str):
    return FileResponse(STATIC / "viewer.html")
