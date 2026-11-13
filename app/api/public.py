"""Публичные эндпоинты для участников: без авторизации, кэшируемые на CDN."""
import asyncio
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Event, Revision
from ..services.bus import bus
from ..services.snapshot import build_snapshot

router = APIRouter(prefix="/v", tags=["public"])


def _event(db: Session, slug: str) -> Event:
    e = db.scalar(select(Event).where(Event.slug == slug))
    if e is None:
        raise HTTPException(404, "мероприятие не найдено")
    return e


@router.get("/{slug}/head")
def head(slug: str, db: Session = Depends(get_db)):
    """Крошечный указатель на актуальную ревизию — единственное, что опрашивается часто."""
    return JSONResponse({"rev": _event(db, slug).head_rev}, headers={"Cache-Control": "public, max-age=5"})


@router.get("/{slug}/snapshots/{rev}.json")
def snapshot(slug: str, rev: int, db: Session = Depends(get_db)):
    """Опубликованный снимок неизменяем → кэшируется навсегда."""
    e = _event(db, slug)
    row = db.scalar(select(Revision).where(Revision.event_id == e.id, Revision.rev == rev))
    if row is None:
        raise HTTPException(404, "ревизия не найдена")
    return JSONResponse(row.snapshot, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/{slug}/staff")
def staff_snapshot(slug: str, token: str = Query(...), db: Session = Depends(get_db)):
    """Карта для своих: живой черновик со всеми полями, включая visible_to=staff. Не кэшируется."""
    e = _event(db, slug)
    if not secrets.compare_digest(token, e.staff_token):
        raise HTTPException(403, "неверный токен")
    return JSONResponse(build_snapshot(db, e, e.head_rev, staff=True).model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


@router.get("/{slug}/stream")
async def stream(slug: str, request: Request):
    """SSE: событие `rev` приходит сразу после публикации; клиент докачивает снимок."""
    item = bus.subscribe(slug)
    q = item[1]

    async def gen():
        try:
            yield "retry: 5000\n\n"
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(q.get(), 15)
                    yield f"event: rev\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(slug, item)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
