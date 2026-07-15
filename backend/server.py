"""PlanMeasure AI — FastAPI backend."""
from __future__ import annotations

import base64
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from analyzer import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    BuildingData,
    DetectedObject,
    aggregate_building_data,
    analyze_document,
    analyze_document_heuristic,
    analyze_floor_plan,
    calibrate_scale,
    recompute_from_objects,
)
from pdf_report import build_report_pdf


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("planmeasure")


# --------------------------------------------------------------------------
# MongoDB (lazy init — avoids crash if env vars missing at import time)
# --------------------------------------------------------------------------
_mongo_client = None
_mongo_db = None
_analyses_col = None


def _get_mongo():
    global _mongo_client, _mongo_db, _analyses_col
    if _analyses_col is None:
        mongo_url = os.environ.get("MONGO_URL", "")
        if not mongo_url:
            raise HTTPException(503, "MONGO_URL not configured")
        db_name = os.environ.get("DB_NAME", "planmeasure")
        _mongo_client = AsyncIOMotorClient(mongo_url)
        _mongo_db = _mongo_client[db_name]
        _analyses_col = _mongo_db["analyses"]
    return _analyses_col

# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
app = FastAPI(title="PlanMeasure AI")
api = APIRouter(prefix="/api")

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_UPLOAD_MB = 20


# --------------------------------------------------------------------------
# Pydantic response models
# --------------------------------------------------------------------------
class AnalysisSummary(BaseModel):
    id: str
    filename: str
    created_at: str
    wall_length: float
    rooms: int
    bathrooms: int
    doors: int
    windows: int
    confidence: float
    approximate: bool
    page_count: int = 1
    analysis_mode: str = "llm"


class ObjectUpdate(BaseModel):
    id: Optional[str] = None
    type: str
    label: Optional[str] = ""
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    points: List[List[float]] = Field(default_factory=list)
    width_ft: Optional[float] = None
    length_ft: Optional[float] = None
    confidence: float = 95.0


class AnalysisUpdate(BaseModel):
    detected_objects: List[ObjectUpdate]
    room_list: Optional[List[Dict[str, Any]]] = None


class CalibrationRequest(BaseModel):
    p1: List[float] = Field(..., min_length=2, max_length=2)
    p2: List[float] = Field(..., min_length=2, max_length=2)
    known_ft: float = Field(..., gt=0)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bd_to_response(bd: BuildingData, doc: Dict[str, Any],
                    page_index: Optional[int] = None) -> Dict[str, Any]:
    """Build API response for /analyze and /analysis/{id}.
    If page_index is provided, preview URL points at that page.
    """
    aid = doc["id"]
    if page_index is not None:
        preview = f"/api/analysis/{aid}/pages/{page_index}/preview"
    else:
        preview = f"/api/analysis/{aid}/preview"
    pages_meta: List[Dict[str, Any]] = []
    for p in doc.get("pages", []) or []:
        pd = p.get("data", {})
        pages_meta.append({
            "page_index": p["page_index"],
            "preview_image": f"/api/analysis/{aid}/pages/{p['page_index']}/preview",
            "wall_length": pd.get("wall_length", 0),
            "rooms": pd.get("rooms", 0),
            "bathrooms": pd.get("bathrooms", 0),
            "doors": pd.get("doors", 0),
            "windows": pd.get("windows", 0),
            "confidence": pd.get("confidence", 0),
            "approximate": pd.get("approximate", True),
        })
    return {
        "id": aid,
        "filename": doc.get("filename", ""),
        "created_at": doc.get("created_at", ""),
        "page_count": doc.get("page_count", 1),
        "page_index": page_index,
        "pages": pages_meta,
        "wall_length": bd.wall_length,
        "external_wall": bd.external_wall,
        "internal_wall": bd.internal_wall,
        "wall_length_m": bd.wall_length_m,
        "external_wall_m": bd.external_wall_m,
        "internal_wall_m": bd.internal_wall_m,
        "rooms": bd.rooms,
        "bathrooms": bd.bathrooms,
        "doors": bd.doors,
        "windows": bd.windows,
        "built_up_area_sqft": bd.built_up_area_sqft,
        "built_up_area_sqm": bd.built_up_area_sqm,
        "confidence": bd.confidence,
        "scale_detected": bd.scale_detected,
        "scale_note": bd.scale_note,
        "approximate": bd.approximate,
        "room_list": bd.room_list,
        "detected_objects": [o.__dict__ for o in bd.detected_objects],
        "preview_width": bd.preview_width,
        "preview_height": bd.preview_height,
        "preview_image": preview,
        "analysis_mode": doc.get("analysis_mode", "llm"),
        "fallback_note": doc.get("fallback_note", ""),
    }


def _dict_to_bd(payload: Dict[str, Any]) -> BuildingData:
    bd = BuildingData(
        wall_length=payload.get("wall_length", 0),
        external_wall=payload.get("external_wall", 0),
        internal_wall=payload.get("internal_wall", 0),
        wall_length_m=payload.get("wall_length_m", 0),
        external_wall_m=payload.get("external_wall_m", 0),
        internal_wall_m=payload.get("internal_wall_m", 0),
        rooms=payload.get("rooms", 0),
        bathrooms=payload.get("bathrooms", 0),
        doors=payload.get("doors", 0),
        windows=payload.get("windows", 0),
        built_up_area_sqft=payload.get("built_up_area_sqft"),
        built_up_area_sqm=payload.get("built_up_area_sqm"),
        confidence=payload.get("confidence", 0),
        scale_detected=payload.get("scale_detected", False),
        scale_note=payload.get("scale_note", ""),
        approximate=payload.get("approximate", True),
        room_list=payload.get("room_list", []),
        preview_width=payload.get("preview_width", 0),
        preview_height=payload.get("preview_height", 0),
    )
    for o in payload.get("detected_objects", []):
        bd.detected_objects.append(DetectedObject(**{k: v for k, v in o.items()
                                                     if k in DetectedObject.__annotations__}))
    return bd


def _doc_to_bd(doc: Dict[str, Any]) -> BuildingData:
    return _dict_to_bd(doc.get("data", {}))


def _reaggregate(doc: Dict[str, Any]) -> BuildingData:
    """Recompute aggregate from per-page BDs and persist to doc['data']."""
    pages = doc.get("pages") or []
    if not pages:
        return _doc_to_bd(doc)
    bds = [_dict_to_bd(p.get("data", {})) for p in pages]
    agg = aggregate_building_data(bds)
    doc["data"] = agg.to_dict()
    return agg


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@api.get("/")
async def root():
    return {"service": "PlanMeasure AI", "version": "1.0"}


@api.get("/health")
async def health():
    return {"status": "ok", "time": _now_iso()}


@api.get("/models")
async def list_models():
    """Return available AI models for floor plan analysis."""
    return {
        "models": [
            {"id": k, "name": v, "free": True}
            for k, v in AVAILABLE_MODELS.items()
        ],
        "default": DEFAULT_MODEL,
    }


@api.post("/analyze")
async def analyze(file: UploadFile = File(...), mode: str = "auto",
                  model: str = DEFAULT_MODEL):
    """Upload a plan and run analysis.
    mode:
      - "llm"       → force Gemini vision (fails if key unavailable)
      - "heuristic" → force OpenCV + Tesseract (LLM-free, offline)
      - "auto"      → try LLM first, fall back to heuristic on quota/error
    model:
      - Gemini model ID (e.g. "gemini-2.5-flash", "gemini-2.0-flash")
    """
    if not file.filename:
        raise HTTPException(400, "No filename")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext}. Allowed: PDF, PNG, JPG")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large (>{MAX_UPLOAD_MB} MB)")

    analysis_id = str(uuid.uuid4())
    logger.info("Analyzing %s (%d bytes) mode=%s model=%s -> %s",
                file.filename, len(raw), mode, model, analysis_id)

    used_mode = mode
    used_model = model
    fallback_note = ""

    if mode not in ("llm", "heuristic", "auto"):
        raise HTTPException(400, "mode must be one of: llm, heuristic, auto")

    async def _try_llm():
        return await analyze_document(raw, file.filename, session_id=analysis_id,
                                      model_name=model)

    def _try_heuristic():
        return analyze_document_heuristic(raw, file.filename)

    try:
        if mode == "heuristic":
            results = _try_heuristic()
            used_mode = "heuristic"
        elif mode == "llm":
            results = await _try_llm()
            used_mode = "llm"
        else:  # auto
            try:
                results = await _try_llm()
                used_mode = "llm"
            except Exception as e:
                # In auto mode, gracefully fall back on ANY LLM failure —
                # the whole point of auto is "give me something usable".
                logger.warning("LLM path failed (%s) — falling back to heuristic", e)
                results = _try_heuristic()
                used_mode = "heuristic"
                msg_low = str(e).lower()
                if any(k in msg_low for k in ("budget", "quota", "insufficient")):
                    fallback_note = ("AI vision quota exhausted — used local heuristic "
                                     "pipeline. Run Calibrate scale for real "
                                     "measurements.")
                elif any(k in msg_low for k in ("not configured", "api_key")):
                    fallback_note = ("AI vision not configured — used local heuristic "
                                     "pipeline. Set GOOGLE_API_KEY in .env for AI analysis.")
                else:
                    fallback_note = ("AI vision temporarily unavailable — used "
                                     "local heuristic pipeline. Run Calibrate "
                                     "scale for real measurements.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Analysis failed")
        msg = str(e)
        low = msg.lower()
        if "not configured" in low or "api_key" in low:
            raise HTTPException(
                status_code=503,
                detail=("AI vision service is not configured. Set GOOGLE_API_KEY "
                        "in .env or use mode=heuristic for the LLM-free pipeline."),
            )
        raise HTTPException(500, f"Analysis failed: {msg}")

    pages_docs: List[Dict[str, Any]] = []
    for i, (bd, png) in enumerate(results):
        pages_docs.append({
            "page_index": i,
            "preview_b64": base64.b64encode(png).decode("ascii"),
            "data": bd.to_dict(),
        })

    aggregate = aggregate_building_data([bd for bd, _ in results])

    doc = {
        "id": analysis_id,
        "filename": file.filename,
        "created_at": _now_iso(),
        "page_count": len(pages_docs),
        "analysis_mode": used_mode,
        "model": used_model,
        "fallback_note": fallback_note,
        "data": aggregate.to_dict(),
        "preview_b64": pages_docs[0]["preview_b64"],
        "pages": pages_docs,
    }
    await _get_mongo().insert_one(doc)

    resp = _bd_to_response(aggregate, doc)
    resp["analysis_mode"] = used_mode
    resp["model"] = used_model
    resp["fallback_note"] = fallback_note
    return resp


@api.get("/analysis/{aid}")
async def get_analysis(aid: str):
    doc = await _get_mongo().find_one(
        {"id": aid},
        # exclude heavy preview blobs; include only page data metadata
        {"_id": 0, "preview_b64": 0, "pages.preview_b64": 0},
    )
    if not doc:
        raise HTTPException(404, "Analysis not found")
    bd = _doc_to_bd(doc)
    return _bd_to_response(bd, doc)


@api.get("/analysis/{aid}/pages/{n}")
async def get_page_analysis(aid: str, n: int):
    doc = await _get_mongo().find_one(
        {"id": aid},
        {"_id": 0, "preview_b64": 0, "pages.preview_b64": 0},
    )
    if not doc:
        raise HTTPException(404, "Analysis not found")
    pages = doc.get("pages") or []
    if not pages:
        # legacy single-page document — page 0 is the whole thing
        if n == 0:
            return _bd_to_response(_doc_to_bd(doc), doc, page_index=0)
        raise HTTPException(404, "Page not found")
    if n < 0 or n >= len(pages):
        raise HTTPException(404, "Page not found")
    bd = _dict_to_bd(pages[n].get("data", {}))
    return _bd_to_response(bd, doc, page_index=n)


@api.get("/analysis/{aid}/pages/{n}/preview")
async def get_page_preview(aid: str, n: int):
    doc = await _get_mongo().find_one({"id": aid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")
    pages = doc.get("pages") or []
    if pages:
        if n < 0 or n >= len(pages):
            raise HTTPException(404, "Page not found")
        b64 = pages[n].get("preview_b64", "")
    else:
        if n != 0:
            raise HTTPException(404, "Page not found")
        b64 = doc.get("preview_b64", "")
    if not b64:
        raise HTTPException(404, "Preview missing")
    return Response(content=base64.b64decode(b64), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@api.get("/analysis/{aid}/preview")
async def get_preview(aid: str):
    doc = await _get_mongo().find_one({"id": aid}, {"_id": 0, "preview_b64": 1})
    if not doc:
        raise HTTPException(404, "Analysis not found")
    b64 = doc.get("preview_b64", "")
    if not b64:
        raise HTTPException(404, "Preview missing")
    png = base64.b64decode(b64)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@api.put("/analysis/{aid}")
async def update_analysis(aid: str, body: AnalysisUpdate, page: int = 0):
    """Apply manual corrections (edit mode) to a specific page (default 0).
    Recomputes counts + wall lengths for that page and re-aggregates.
    """
    doc = await _get_mongo().find_one({"id": aid}, {"_id": 0, "preview_b64": 0,
                                                     "pages.preview_b64": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")

    pages = doc.get("pages") or []
    target_bd: BuildingData
    if pages:
        if page < 0 or page >= len(pages):
            raise HTTPException(404, "Page not found")
        target_bd = _dict_to_bd(pages[page].get("data", {}))
    else:
        target_bd = _doc_to_bd(doc)

    new_objs: List[DetectedObject] = []
    for i, o in enumerate(body.detected_objects):
        new_objs.append(DetectedObject(
            id=o.id or f"obj_{i}",
            type=o.type,
            label=o.label or "",
            x=o.x, y=o.y, w=o.w, h=o.h,
            points=o.points or [],
            width_ft=o.width_ft,
            length_ft=o.length_ft,
            confidence=o.confidence,
        ))
    target_bd.detected_objects = new_objs
    if body.room_list is not None:
        target_bd.room_list = body.room_list

    target_bd = recompute_from_objects(target_bd)

    if pages:
        pages[page]["data"] = target_bd.to_dict()
        doc["pages"] = pages
        agg = _reaggregate(doc)
        await _get_mongo().update_one(
            {"id": aid},
            {"$set": {
                f"pages.{page}.data": target_bd.to_dict(),
                "data": agg.to_dict(),
                "updated_at": _now_iso(),
            }},
        )
        return _bd_to_response(target_bd, doc, page_index=page)
    # Legacy single-page path
    await _get_mongo().update_one(
        {"id": aid},
        {"$set": {"data": target_bd.to_dict(), "updated_at": _now_iso()}},
    )
    doc["data"] = target_bd.to_dict()
    return _bd_to_response(target_bd, doc)


@api.get("/analyses", response_model=List[AnalysisSummary])
async def list_analyses():
    cursor = _get_mongo().find({}, {"_id": 0, "preview_b64": 0}).sort("created_at", -1).limit(50)
    out: List[AnalysisSummary] = []
    async for d in cursor:
        data = d.get("data", {})
        out.append(AnalysisSummary(
            id=d["id"],
            filename=d.get("filename", ""),
            created_at=d.get("created_at", ""),
            wall_length=data.get("wall_length", 0),
            rooms=data.get("rooms", 0),
            bathrooms=data.get("bathrooms", 0),
            doors=data.get("doors", 0),
            windows=data.get("windows", 0),
            confidence=data.get("confidence", 0),
            approximate=data.get("approximate", True),
            page_count=d.get("page_count", 1),
            analysis_mode=d.get("analysis_mode", "llm"),
        ))
    return out


@api.delete("/analysis/{aid}")
async def delete_analysis(aid: str):
    r = await _get_mongo().delete_one({"id": aid})
    if r.deleted_count == 0:
        raise HTTPException(404, "Analysis not found")
    return {"deleted": True}


@api.post("/analysis/{aid}/calibrate")
async def calibrate(aid: str, body: CalibrationRequest, page: int = 0):
    """Apply a user-drawn scale calibration to a specific page (default 0)."""
    doc = await _get_mongo().find_one({"id": aid}, {"_id": 0, "preview_b64": 0,
                                                     "pages.preview_b64": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")

    pages = doc.get("pages") or []
    if pages:
        if page < 0 or page >= len(pages):
            raise HTTPException(404, "Page not found")
        bd = _dict_to_bd(pages[page].get("data", {}))
    else:
        bd = _doc_to_bd(doc)

    if bd.preview_width <= 0 or bd.preview_height <= 0:
        raise HTTPException(400, "Preview dimensions missing")
    dx = (body.p2[0] - body.p1[0]) * bd.preview_width
    dy = (body.p2[1] - body.p1[1]) * bd.preview_height
    if (dx * dx + dy * dy) < 4.0:
        raise HTTPException(400, "Segment too short — draw a longer reference segment.")

    bd = calibrate_scale(bd, body.p1, body.p2, body.known_ft)
    bd = recompute_from_objects(bd)

    if pages:
        pages[page]["data"] = bd.to_dict()
        doc["pages"] = pages
        agg = _reaggregate(doc)
        await _get_mongo().update_one(
            {"id": aid},
            {"$set": {
                f"pages.{page}.data": bd.to_dict(),
                "data": agg.to_dict(),
                "updated_at": _now_iso(),
            }},
        )
        return _bd_to_response(bd, doc, page_index=page)
    await _get_mongo().update_one(
        {"id": aid},
        {"$set": {"data": bd.to_dict(), "updated_at": _now_iso()}},
    )
    doc["data"] = bd.to_dict()
    return _bd_to_response(bd, doc)


@api.get("/analysis/{aid}/report")
async def download_report(aid: str):
    doc = await _get_mongo().find_one({"id": aid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")

    # Build list of (page_index, data_dict, preview_png_bytes|None)
    pages_payload: List[Tuple[int, Dict[str, Any], Optional[bytes]]] = []
    doc_pages = doc.get("pages") or []
    if doc_pages:
        for p in doc_pages:
            png = None
            b64 = p.get("preview_b64", "")
            if b64:
                try:
                    png = base64.b64decode(b64)
                except Exception:
                    png = None
            pages_payload.append((p["page_index"], p.get("data", {}), png))
    else:
        png = None
        b64 = doc.get("preview_b64", "")
        if b64:
            try:
                png = base64.b64decode(b64)
            except Exception:
                png = None
        pages_payload.append((0, doc.get("data", {}), png))

    pdf = build_report_pdf(
        doc.get("data", {}),
        pages_payload[0][2],
        doc.get("filename", "plan"),
        pages=pages_payload,
    )
    safe_name = os.path.splitext(doc.get("filename", "plan"))[0]
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="planmeasure_{safe_name}.pdf"'},
    )


# --------------------------------------------------------------------------
# App wiring
# --------------------------------------------------------------------------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    if _mongo_client:
        _mongo_client.close()