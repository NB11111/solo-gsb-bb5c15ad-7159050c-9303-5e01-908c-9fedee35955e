"""FastAPI 入口：样本与交接事件 CRUD、审计、报告导出。"""
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import audit as audit_mod
from . import database as db
from .report import build_html, build_markdown
from .schemas import EventCreate, SampleCreate

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时完成数据库初始化（表结构 + 数据目录）
    db.init_db()
    yield


app = FastAPI(title="样本交接链路审计", version="1.0.0", lifespan=lifespan)


# ---------------- 辅助 ----------------

def _sample_or_404(conn: sqlite3.Connection, sample_id: int) -> sqlite3.Row:
    sample = db.get_sample(conn, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    return sample


def _event_or_404(conn: sqlite3.Connection, event_id: int) -> sqlite3.Row:
    event = db.get_event(conn, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return event


def _run_audit(conn: sqlite3.Connection, sample_id: int,
               gap_hours: float) -> dict:
    sample = _sample_or_404(conn, sample_id)
    events = db.list_events(conn, sample_id)
    result = audit_mod.audit(events, gap_hours=gap_hours)
    result["sample"] = dict(sample)
    return result


def _conflict_error(exc: sqlite3.IntegrityError) -> HTTPException:
    if "UNIQUE" in str(exc).upper():
        return HTTPException(status_code=409, detail="样本编号已存在")
    raise HTTPException(status_code=400, detail=f"数据错误：{exc}")


# ---------------- 样本 ----------------

@app.get("/api/samples")
def api_list_samples():
    with db.get_conn() as conn:
        return [dict(r) for r in db.list_samples(conn)]


@app.post("/api/samples", status_code=201)
def api_create_sample(payload: SampleCreate):
    with db.get_conn() as conn:
        try:
            row = db.create_sample(conn, payload.code, payload.name,
                                   payload.description)
        except sqlite3.IntegrityError as exc:
            raise _conflict_error(exc)
        return dict(row)


@app.get("/api/samples/{sample_id}")
def api_get_sample(sample_id: int):
    with db.get_conn() as conn:
        return dict(_sample_or_404(conn, sample_id))


@app.put("/api/samples/{sample_id}")
def api_update_sample(sample_id: int, payload: SampleCreate):
    with db.get_conn() as conn:
        _sample_or_404(conn, sample_id)
        try:
            row = db.update_sample(conn, sample_id, payload.code, payload.name,
                                   payload.description)
        except sqlite3.IntegrityError as exc:
            raise _conflict_error(exc)
        return dict(row)


@app.delete("/api/samples/{sample_id}", status_code=204)
def api_delete_sample(sample_id: int):
    with db.get_conn() as conn:
        _sample_or_404(conn, sample_id)
        db.delete_sample(conn, sample_id)
    return Response(status_code=204)


# ---------------- 交接事件 ----------------

@app.post("/api/samples/{sample_id}/events", status_code=201)
def api_create_event(sample_id: int, payload: EventCreate):
    with db.get_conn() as conn:
        _sample_or_404(conn, sample_id)
        row = db.create_event(
            conn, sample_id, payload.naive_iso(),
            payload.from_party, payload.to_party,
            payload.location, payload.note,
        )
        return dict(row)


@app.put("/api/events/{event_id}")
def api_update_event(event_id: int, payload: EventCreate):
    with db.get_conn() as conn:
        row = _event_or_404(conn, event_id)
        row = db.update_event(
            conn, event_id, payload.naive_iso(),
            payload.from_party, payload.to_party,
            payload.location, payload.note,
        )
        return dict(row)


@app.delete("/api/events/{event_id}", status_code=204)
def api_delete_event(event_id: int):
    with db.get_conn() as conn:
        _event_or_404(conn, event_id)
        db.delete_event(conn, event_id)
    return Response(status_code=204)


# ---------------- 审计与报告 ----------------

@app.get("/api/samples/{sample_id}/audit")
def api_audit(
    sample_id: int,
    gap_hours: float = Query(default=audit_mod.DEFAULT_GAP_HOURS, ge=0,
                             description="时间断档阈值（小时）"),
):
    with db.get_conn() as conn:
        return _run_audit(conn, sample_id, gap_hours)


@app.get("/api/samples/{sample_id}/report")
def api_report(
    sample_id: int,
    fmt: str = Query(default="markdown", pattern="^(markdown|html)$"),
    gap_hours: float = Query(default=audit_mod.DEFAULT_GAP_HOURS, ge=0),
):
    with db.get_conn() as conn:
        result = _run_audit(conn, sample_id, gap_hours)

    sample = result["sample"]
    filename = f"audit_report_{sample['code']}"
    if fmt == "markdown":
        text = build_markdown(sample, result)
        return PlainTextResponse(
            text,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition":
                     f"attachment; filename*=UTF-8''{quote(filename)}.md"},
        )
    html = build_html(sample, result)
    return HTMLResponse(
        html,
        headers={"Content-Disposition":
                 f"attachment; filename*=UTF-8''{quote(filename)}.html"},
    )


# ---------------- 前端静态页 ----------------

@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
