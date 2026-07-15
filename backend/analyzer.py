"""
Floor Plan Analyzer Module
Modular architecture: Extracts structured BuildingData from a floor plan image.
Future modules (BOQ, Brick Calculator, Paint Calculator, Cost Estimator, etc.)
will consume the same BuildingData dataclass returned by `analyze_floor_plan`.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image
import cv2
import numpy as np

from dotenv import load_dotenv

# Ensure .env is loaded even if analyzer is imported before server.py's load_dotenv
load_dotenv(Path(__file__).parent / ".env")


# Available free Gemini models
AVAILABLE_MODELS = {
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-flash-lite": "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.0-flash": "gemini-2.0-flash",
}

DEFAULT_MODEL = "gemini-2.5-flash"


def _get_api_key() -> str:
    return os.environ.get("GOOGLE_API_KEY", "")


# ---------------------------------------------------------------------------
# Data model (shared across future modules: BOQ, brick, plaster, paint, cost)
# ---------------------------------------------------------------------------
@dataclass
class DetectedObject:
    id: str
    type: str  # wall_external | wall_internal | door | window | room | bathroom
    label: str = ""
    # Normalized bounding box (0..1) relative to preview image
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    # Optional polyline for walls (list of [x,y] normalized)
    points: List[List[float]] = field(default_factory=list)
    width_ft: Optional[float] = None
    length_ft: Optional[float] = None
    confidence: float = 90.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildingData:
    wall_length: float = 0.0        # feet
    external_wall: float = 0.0      # feet
    internal_wall: float = 0.0      # feet
    wall_length_m: float = 0.0      # meters
    external_wall_m: float = 0.0
    internal_wall_m: float = 0.0
    rooms: int = 0
    bathrooms: int = 0
    doors: int = 0
    windows: int = 0
    built_up_area_sqft: Optional[float] = None
    built_up_area_sqm: Optional[float] = None
    confidence: float = 0.0
    scale_detected: bool = False
    scale_note: str = ""
    detected_objects: List[DetectedObject] = field(default_factory=list)
    room_list: List[Dict[str, Any]] = field(default_factory=list)
    approximate: bool = True
    preview_width: int = 0
    preview_height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Image pipeline
# ---------------------------------------------------------------------------
FT_TO_M = 0.3048


def pdf_to_image(pdf_bytes: bytes, dpi: int = 200) -> bytes:
    """Convert first page of PDF to a high-res PNG. Returns bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


MAX_PDF_PAGES = 8


def pdf_all_pages_to_images(pdf_bytes: bytes, dpi: int = 200,
                            max_pages: int = MAX_PDF_PAGES) -> List[bytes]:
    """Convert up to `max_pages` PDF pages to PNG byte lists (in order)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: List[bytes] = []
    for i in range(min(doc.page_count, max_pages)):
        page = doc.load_page(i)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        out.append(pix.tobytes("png"))
    doc.close()
    return out


def normalize_input_to_png(file_bytes: bytes, filename: str) -> bytes:
    """Accepts pdf/jpg/png bytes, returns PNG bytes suitable for analysis."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return pdf_to_image(file_bytes)
    # For jpg/png, decode + re-encode as PNG (also handles WebP etc.)
    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    # Cap max size to keep upload reasonable
    max_side = 2400
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def cv_wall_stats(png_bytes: bytes) -> Dict[str, Any]:
    """
    Lightweight OpenCV pre-pass — detects candidate line segments.
    Provides a rough count/length feature that can bias the LLM's estimate
    when no scale is available. Kept optional / non-blocking.
    """
    try:
        arr = np.frombuffer(png_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {}
        h, w = img.shape[:2]
        # Adaptive threshold + edges
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=100,
            minLineLength=max(w, h) // 40, maxLineGap=8
        )
        segments = 0
        total_px = 0.0
        if lines is not None:
            segments = len(lines)
            for l in lines:
                x1, y1, x2, y2 = l[0]
                total_px += float(np.hypot(x2 - x1, y2 - y1))
        return {
            "img_w": w, "img_h": h,
            "line_segments": int(segments),
            "line_pixels_total": float(total_px),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# LLM Vision analysis using Google Generative AI SDK
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are PlanMeasure AI, an expert architectural floor plan analyzer.
You will be given a single floor plan image (residential or commercial).
Return a STRICT JSON object (no markdown, no commentary) with the following schema:

{
  "wall_length": <total wall length in FEET, number>,
  "external_wall": <external walls length in feet, number>,
  "internal_wall": <internal walls length in feet, number>,
  "rooms": <total room count, integer>,
  "bathrooms": <bathroom count, integer>,
  "doors": <door count, integer>,
  "windows": <window count, integer>,
  "built_up_area_sqft": <built-up / floor area in sq ft or null if not detectable>,
  "confidence": <overall confidence 0-100, integer>,
  "scale_detected": <true|false — whether the drawing has a readable scale or dimensions>,
  "scale_note": <"" or short human note e.g. "Scale 1:100 detected" / "No scale — approximate">,
  "approximate": <true|false>,
  "room_list": [ {"name": "Living Room", "area_sqft": 220, "is_bathroom": false}, ... ],
  "detected_objects": [
     {
       "id": "wall_1",
       "type": "wall_external" | "wall_internal" | "door" | "window" | "room" | "bathroom",
       "label": "e.g. Bedroom 1 / Door #1",
       "x": <normalized 0..1 top-left>,
       "y": <normalized 0..1 top-left>,
       "w": <normalized 0..1 width>,
       "h": <normalized 0..1 height>,
       "points": [[x1,y1],[x2,y2], ...],   // for walls only, polyline in normalized coords, [] otherwise
       "width_ft": <opening width for door/window in ft, or null>,
       "length_ft": <segment length in ft for walls, or null>,
       "confidence": <0-100>
     }
  ]
}

Rules:
- If dimensions are annotated on the plan, use them to compute lengths. Otherwise estimate using standard residential proportions and clearly set approximate=true and confidence <= 75.
- Provide bounding boxes for every door, window, room, bathroom. Walls should include a `points` polyline.
- Every room MUST also appear in `room_list` in reading order.
- Bathrooms are rooms too, but also counted in `bathrooms`.
- Return ONLY the JSON. No prose. No markdown fences.
"""


def _extract_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from LLM response."""
    # Strip common markdown fences
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    # Try direct parse
    try:
        return json.loads(t)
    except Exception:
        pass
    # Find first { and last }
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except Exception:
            pass
    return {}


async def llm_analyze(png_bytes: bytes, session_id: str, cv_hint: Dict[str, Any],
                      model_name: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """Run Gemini vision analysis and return parsed JSON dict."""
    import google.generativeai as genai

    key = _get_api_key()
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not configured")

    genai.configure(api_key=key)

    # Resolve model name
    resolved_model = AVAILABLE_MODELS.get(model_name, model_name)

    # Build the model with system instruction
    model = genai.GenerativeModel(
        model_name=resolved_model,
        system_instruction=_SYSTEM_PROMPT,
    )

    # Prepare image
    b64 = base64.b64encode(png_bytes).decode("ascii")
    image_part = {
        "mime_type": "image/png",
        "data": b64,
    }

    hint_text = ""
    if cv_hint:
        hint_text = (
            f"\n\n(Pre-analysis hint — OpenCV detected ~{cv_hint.get('line_segments', 0)} "
            f"line segments across a {cv_hint.get('img_w')}x{cv_hint.get('img_h')} image. "
            "Use this as sanity check for wall counts.)"
        )

    prompt = "Analyze this floor plan and return the strict JSON per system spec." + hint_text

    response = await model.generate_content_async(
        [prompt, image_part],
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )

    text = response.text
    data = _extract_json(text)
    if not data:
        raise ValueError(f"LLM returned unparseable response: {text[:400]}")
    return data


# ---------------------------------------------------------------------------
# High-level orchestrator
# ---------------------------------------------------------------------------
def _coerce_num(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _coerce_int(v, default=0):
    try:
        if v is None:
            return default
        return int(round(float(v)))
    except Exception:
        return default


def build_building_data(llm_json: Dict[str, Any], img_w: int, img_h: int) -> BuildingData:
    total_ft = _coerce_num(llm_json.get("wall_length"))
    ext_ft = _coerce_num(llm_json.get("external_wall"))
    int_ft = _coerce_num(llm_json.get("internal_wall"))
    # Sanity: if internal+external ~= total keep, else recompute
    if total_ft <= 0 and (ext_ft + int_ft) > 0:
        total_ft = ext_ft + int_ft

    bd = BuildingData(
        wall_length=round(total_ft, 1),
        external_wall=round(ext_ft, 1),
        internal_wall=round(int_ft, 1),
        wall_length_m=round(total_ft * FT_TO_M, 2),
        external_wall_m=round(ext_ft * FT_TO_M, 2),
        internal_wall_m=round(int_ft * FT_TO_M, 2),
        rooms=_coerce_int(llm_json.get("rooms")),
        bathrooms=_coerce_int(llm_json.get("bathrooms")),
        doors=_coerce_int(llm_json.get("doors")),
        windows=_coerce_int(llm_json.get("windows")),
        built_up_area_sqft=(_coerce_num(llm_json.get("built_up_area_sqft"))
                            if llm_json.get("built_up_area_sqft") not in (None, "", 0) else None),
        confidence=_coerce_num(llm_json.get("confidence"), 80.0),
        scale_detected=bool(llm_json.get("scale_detected")),
        scale_note=str(llm_json.get("scale_note") or ""),
        approximate=bool(llm_json.get("approximate", True)),
        room_list=llm_json.get("room_list") or [],
        preview_width=img_w,
        preview_height=img_h,
    )
    if bd.built_up_area_sqft:
        bd.built_up_area_sqm = round(bd.built_up_area_sqft * 0.092903, 2)

    for i, o in enumerate(llm_json.get("detected_objects") or []):
        try:
            bd.detected_objects.append(DetectedObject(
                id=str(o.get("id") or f"obj_{i}"),
                type=str(o.get("type") or "wall_internal"),
                label=str(o.get("label") or ""),
                x=_coerce_num(o.get("x")),
                y=_coerce_num(o.get("y")),
                w=_coerce_num(o.get("w")),
                h=_coerce_num(o.get("h")),
                points=o.get("points") or [],
                width_ft=(_coerce_num(o.get("width_ft"))
                          if o.get("width_ft") not in (None, "") else None),
                length_ft=(_coerce_num(o.get("length_ft"))
                           if o.get("length_ft") not in (None, "") else None),
                confidence=_coerce_num(o.get("confidence"), 90.0),
            ))
        except Exception:
            continue

    return bd


async def analyze_floor_plan(file_bytes: bytes, filename: str, session_id: str,
                             model_name: str = DEFAULT_MODEL
                             ) -> Tuple[BuildingData, bytes]:
    """Legacy single-page pipeline (kept for backwards compat)."""
    png = normalize_input_to_png(file_bytes, filename)
    img = Image.open(io.BytesIO(png))
    w, h = img.size
    cv_hint = cv_wall_stats(png)
    llm_json = await llm_analyze(png, session_id, cv_hint, model_name=model_name)
    bd = build_building_data(llm_json, w, h)
    return bd, png


async def analyze_document(file_bytes: bytes, filename: str, session_id: str,
                           model_name: str = DEFAULT_MODEL
                           ) -> List[Tuple[BuildingData, bytes]]:
    """
    Multi-page pipeline. For PDFs, analyzes every page (up to MAX_PDF_PAGES).
    For PNG/JPG, returns a single-item list.
    Returns list of (BuildingData, preview_png_bytes) — one per page in order.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        pngs = pdf_all_pages_to_images(file_bytes)
        if not pngs:
            raise ValueError("PDF has no readable pages")
    else:
        pngs = [normalize_input_to_png(file_bytes, filename)]

    out: List[Tuple[BuildingData, bytes]] = []
    for i, png in enumerate(pngs):
        img = Image.open(io.BytesIO(png))
        w, h = img.size
        cv_hint = cv_wall_stats(png)
        llm_json = await llm_analyze(png, f"{session_id}_p{i}", cv_hint,
                                     model_name=model_name)
        bd = build_building_data(llm_json, w, h)
        out.append((bd, png))
    return out


def analyze_document_heuristic(file_bytes: bytes, filename: str
                               ) -> List[Tuple[BuildingData, bytes]]:
    """
    Pure OpenCV + Tesseract multi-page pipeline (no LLM). Returns same shape
    as `analyze_document`. Wall lengths are zero until user calibrates scale.
    """
    from heuristic_analyzer import analyze_heuristic
    lower = filename.lower()
    if lower.endswith(".pdf"):
        pngs = pdf_all_pages_to_images(file_bytes)
        if not pngs:
            raise ValueError("PDF has no readable pages")
    else:
        pngs = [normalize_input_to_png(file_bytes, filename)]

    out: List[Tuple[BuildingData, bytes]] = []
    for png in pngs:
        img = Image.open(io.BytesIO(png))
        w, h = img.size
        result = analyze_heuristic(png)
        bd = build_building_data(result, w, h)
        out.append((bd, png))
    return out


def aggregate_building_data(bds: List[BuildingData]) -> BuildingData:
    """
    Combine per-page BuildingData into an aggregate view.
    Sums counts + wall lengths, weight-averages confidence, unions room_list
    with a `page` prefix, marks approximate=true if any page is approximate.
    """
    if not bds:
        return BuildingData()
    if len(bds) == 1:
        return bds[0]

    total = sum(b.wall_length for b in bds)
    ext = sum(b.external_wall for b in bds)
    intr = sum(b.internal_wall for b in bds)
    agg = BuildingData(
        wall_length=round(total, 1),
        external_wall=round(ext, 1),
        internal_wall=round(intr, 1),
        wall_length_m=round(total * FT_TO_M, 2),
        external_wall_m=round(ext * FT_TO_M, 2),
        internal_wall_m=round(intr * FT_TO_M, 2),
        rooms=sum(b.rooms for b in bds),
        bathrooms=sum(b.bathrooms for b in bds),
        doors=sum(b.doors for b in bds),
        windows=sum(b.windows for b in bds),
        confidence=round(sum(b.confidence for b in bds) / len(bds), 1),
        scale_detected=all(b.scale_detected for b in bds),
        scale_note="Aggregated across pages",
        approximate=any(b.approximate for b in bds),
    )
    areas = [b.built_up_area_sqft for b in bds if b.built_up_area_sqft]
    if areas:
        agg.built_up_area_sqft = round(sum(areas), 1)
        agg.built_up_area_sqm = round(agg.built_up_area_sqft * 0.092903, 2)

    rooms_flat: List[Dict[str, Any]] = []
    for i, b in enumerate(bds):
        for r in b.room_list:
            r2 = dict(r)
            r2["page"] = i + 1
            rooms_flat.append(r2)
    agg.room_list = rooms_flat
    # detected_objects intentionally empty at aggregate level — they live
    # per-page and are fetched via /pages/{n}
    agg.detected_objects = []
    agg.preview_width = bds[0].preview_width
    agg.preview_height = bds[0].preview_height
    return agg


# Recompute helper (used by manual-correction endpoint so future modules
# like BOQ / Paint / Brick can trigger recompute after edits)
def calibrate_scale(bd: BuildingData, p1: List[float], p2: List[float], known_ft: float) -> BuildingData:
    """
    Apply user-supplied scale calibration.
    p1, p2 are normalized coords [x,y] in 0..1 relative to preview.
    known_ft is the real-world length of the drawn segment in feet.
    Rescales every wall polyline (length_ft) and every door/window (width_ft),
    plus built-up area from any room bboxes.
    """
    if known_ft <= 0 or bd.preview_width <= 0 or bd.preview_height <= 0:
        return bd
    dx_px = (p2[0] - p1[0]) * bd.preview_width
    dy_px = (p2[1] - p1[1]) * bd.preview_height
    seg_px = (dx_px * dx_px + dy_px * dy_px) ** 0.5
    if seg_px <= 0:
        return bd
    ft_per_px = known_ft / seg_px

    ext = 0.0
    intr = 0.0
    for o in bd.detected_objects:
        t = o.type
        if t in ("wall_external", "wall_internal") and o.points and len(o.points) >= 2:
            total = 0.0
            for i in range(1, len(o.points)):
                a, b = o.points[i - 1], o.points[i]
                px = (b[0] - a[0]) * bd.preview_width
                py = (b[1] - a[1]) * bd.preview_height
                total += (px * px + py * py) ** 0.5
            o.length_ft = round(total * ft_per_px, 1)
            if t == "wall_external":
                ext += o.length_ft
            else:
                intr += o.length_ft
        elif t == "door":
            side = max(o.w * bd.preview_width, o.h * bd.preview_height)
            o.width_ft = round(side * ft_per_px, 1)
        elif t == "window":
            side = max(o.w * bd.preview_width, o.h * bd.preview_height)
            o.width_ft = round(side * ft_per_px, 1)

    bd.external_wall = round(ext, 1)
    bd.internal_wall = round(intr, 1)
    bd.wall_length = round(ext + intr, 1)
    bd.external_wall_m = round(bd.external_wall * FT_TO_M, 2)
    bd.internal_wall_m = round(bd.internal_wall * FT_TO_M, 2)
    bd.wall_length_m = round(bd.wall_length * FT_TO_M, 2)

    # Built-up area: sum of rect areas of type room + bathroom in ft^2
    total_area = 0.0
    for o in bd.detected_objects:
        if o.type in ("room", "bathroom") and o.w and o.h:
            w_ft = (o.w * bd.preview_width) * ft_per_px
            h_ft = (o.h * bd.preview_height) * ft_per_px
            total_area += w_ft * h_ft
    if total_area > 0:
        bd.built_up_area_sqft = round(total_area, 1)
        bd.built_up_area_sqm = round(total_area * 0.092903, 2)

    bd.scale_detected = True
    bd.scale_note = f"User calibrated · {ft_per_px:.4f} ft/px"
    bd.approximate = False
    bd.confidence = max(bd.confidence, 92.0)
    return bd


def recompute_from_objects(bd: BuildingData) -> BuildingData:
    """Recompute counts and wall lengths from detected_objects list."""
    ext = 0.0
    intr = 0.0
    doors = 0
    windows = 0
    rooms = 0
    baths = 0
    for o in bd.detected_objects:
        t = o.type
        if t == "wall_external":
            if o.length_ft:
                ext += o.length_ft
        elif t == "wall_internal":
            if o.length_ft:
                intr += o.length_ft
        elif t == "door":
            doors += 1
        elif t == "window":
            windows += 1
        elif t == "room":
            rooms += 1
        elif t == "bathroom":
            baths += 1
            rooms += 1
    # Only override if we actually captured lengths; else keep LLM totals
    if ext + intr > 0:
        bd.external_wall = round(ext, 1)
        bd.internal_wall = round(intr, 1)
        bd.wall_length = round(ext + intr, 1)
        bd.external_wall_m = round(ext * FT_TO_M, 2)
        bd.internal_wall_m = round(intr * FT_TO_M, 2)
        bd.wall_length_m = round((ext + intr) * FT_TO_M, 2)
    bd.doors = doors
    bd.windows = windows
    if rooms > 0:
        bd.rooms = rooms
    if baths > 0:
        bd.bathrooms = baths
    return bd