"""
Heuristic (LLM-free) floor plan analyzer.
Uses OpenCV for wall/line detection and Tesseract for room-label OCR.
Produces the same BuildingData shape as the Gemini vision path, so all
downstream code (PDF report, edit mode, calibration) works unchanged.

Accuracy is lower than the vision model — use manual correction + scale
calibration to refine the output.
"""
from __future__ import annotations

import io
import re
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image

try:
    import pytesseract  # type: ignore
    _OCR_AVAILABLE = True
except Exception:
    _OCR_AVAILABLE = False


BATHROOM_KEYWORDS = ("bath", "toilet", " wc", "washroom", "w.c", "powder", "shower")
COMMON_ROOM_KEYWORDS = (
    "bed", "kitchen", "living", "dining", "lounge", "hall", "study",
    "garage", "utility", "laundry", "office", "master", "guest",
    "family", "porch", "balcony", "foyer", "stair", "closet",
) + BATHROOM_KEYWORDS


# ---------------------------------------------------------------------------
# Wall detection
# ---------------------------------------------------------------------------
def _detect_walls(gray: np.ndarray, W: int, H: int) -> List[Dict]:
    """Detect long-ish line segments via Canny + probabilistic Hough."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    min_len = max(30, min(W, H) // 25)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=90,
        minLineLength=min_len, maxLineGap=12,
    )
    walls: List[Dict] = []
    if lines is None:
        return walls
    for i, l in enumerate(lines):
        arr_ = np.asarray(l).flatten()
        x1, y1, x2, y2 = int(arr_[0]), int(arr_[1]), int(arr_[2]), int(arr_[3])
        length_px = float(np.hypot(x2 - x1, y2 - y1))
        # Skip near-diagonal noise: keep mostly-orthogonal walls
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dx > 4 and dy > 4 and abs(dx - dy) < 4:
            continue
        walls.append({
            "id": f"wall_{i}",
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "length_px": length_px,
        })
    return walls


def _classify_and_pack_walls(walls: List[Dict], W: int, H: int
                             ) -> Tuple[List[Dict], float, float]:
    """Split walls into external vs internal + total pixel lengths.
    External heuristic: any endpoint within `border_margin` of the image edge.
    """
    border_margin = 0.12
    out: List[Dict] = []
    ext_px = 0.0
    int_px = 0.0
    for i, w in enumerate(walls):
        x1n = w["x1"] / W
        y1n = w["y1"] / H
        x2n = w["x2"] / W
        y2n = w["y2"] / H
        near_border = (
            min(x1n, x2n) < border_margin or max(x1n, x2n) > 1 - border_margin
            or min(y1n, y2n) < border_margin or max(y1n, y2n) > 1 - border_margin
        )
        wtype = "wall_external" if near_border else "wall_internal"
        if near_border:
            ext_px += w["length_px"]
        else:
            int_px += w["length_px"]
        out.append({
            "id": f"w_{i}",
            "type": wtype,
            "label": ("External wall" if near_border else "Internal wall") + f" {i + 1}",
            "x": min(x1n, x2n),
            "y": min(y1n, y2n),
            "w": max(0.002, abs(x2n - x1n)),
            "h": max(0.002, abs(y2n - y1n)),
            "points": [[x1n, y1n], [x2n, y2n]],
            "length_ft": None,
            "width_ft": None,
            "confidence": 60,
            "extra": {},
        })
    return out, ext_px, int_px


# ---------------------------------------------------------------------------
# OCR: room labels
# ---------------------------------------------------------------------------
def _ocr_rooms(pil_img: Image.Image) -> List[Dict]:
    if not _OCR_AVAILABLE:
        return []
    W, H = pil_img.size
    try:
        data = pytesseract.image_to_data(
            pil_img, output_type=pytesseract.Output.DICT,
            config="--psm 12",  # sparse text with OSD — good for floor plans
        )
    except Exception:
        return []

    tokens: List[Dict] = []
    n = len(data.get("text", []))
    for i in range(n):
        raw = (data["text"][i] or "").strip()
        if not raw:
            continue
        try:
            conf = int(float(data["conf"][i]))
        except Exception:
            conf = -1
        if conf < 40:
            continue
        if not re.search(r"[A-Za-z]{3,}", raw):
            continue
        lower = raw.lower()
        # Only accept tokens that look like room labels
        if not any(k in lower for k in COMMON_ROOM_KEYWORDS):
            continue
        x = data["left"][i] / W
        y = data["top"][i] / H
        w = max(data["width"][i] / W, 0.02)
        h = max(data["height"][i] / H, 0.02)
        is_bath = any(k in lower for k in BATHROOM_KEYWORDS)
        tokens.append({
            "text": raw,
            "x": x, "y": y, "w": w, "h": h,
            "confidence": conf,
            "is_bathroom": is_bath,
        })

    # Deduplicate: cluster tokens within ~5% of each other in both axes
    dedup: List[Dict] = []
    for t in tokens:
        merged = False
        for d in dedup:
            if abs(d["x"] - t["x"]) < 0.05 and abs(d["y"] - t["y"]) < 0.05:
                merged = True
                break
        if not merged:
            dedup.append(t)
    return dedup


# ---------------------------------------------------------------------------
# Door/window opening detection (very light heuristic)
# ---------------------------------------------------------------------------
def _detect_openings(gray: np.ndarray, W: int, H: int
                     ) -> Tuple[List[Dict], List[Dict]]:
    """Doors ≈ short arcs (HoughCircles on high threshold).
    Windows ≈ short parallel double-line pairs — hard to detect reliably,
    so we return an empty list and let the user add via edit mode.
    """
    doors: List[Dict] = []
    try:
        blur = cv2.medianBlur(gray, 5)
        circles = cv2.HoughCircles(
            blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(20, min(W, H) // 40),
            param1=100, param2=45,
            minRadius=max(8, min(W, H) // 120),
            maxRadius=max(20, min(W, H) // 30),
        )
        if circles is not None:
            for i, c in enumerate(np.round(circles[0]).astype(int)):
                cx, cy, r = c
                doors.append({
                    "id": f"d_{i}",
                    "type": "door",
                    "label": f"Door {i + 1}",
                    "x": max(0.0, (cx - r) / W),
                    "y": max(0.0, (cy - r) / H),
                    "w": min(1.0, (2 * r) / W),
                    "h": min(1.0, (2 * r) / H),
                    "points": [],
                    "length_ft": None,
                    "width_ft": None,
                    "confidence": 55,
                    "extra": {},
                })
    except Exception:
        pass
    windows: List[Dict] = []
    return doors, windows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_heuristic(png_bytes: bytes) -> Dict:
    """Analyse a floor plan PNG with pure OpenCV + Tesseract.
    Returns a dict with the same shape as the LLM JSON (see analyzer.build_building_data).
    Wall lengths are ZERO until the user runs Scale Calibration — polylines
    are populated so calibration converts them to real feet in one call.
    """
    pil_img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    W, H = pil_img.size
    arr = np.array(pil_img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    raw_walls = _detect_walls(gray, W, H)
    wall_objs, _ext_px, _int_px = _classify_and_pack_walls(raw_walls, W, H)

    door_objs, window_objs = _detect_openings(gray, W, H)

    room_tokens = _ocr_rooms(pil_img)
    room_objs: List[Dict] = []
    room_list: List[Dict] = []
    bath_count = 0
    for i, t in enumerate(room_tokens):
        otype = "bathroom" if t["is_bathroom"] else "room"
        # Expand tight OCR bbox into a plausible room bbox
        room_objs.append({
            "id": f"r_{i}",
            "type": otype,
            "label": t["text"],
            "x": max(0.0, t["x"] - 0.06),
            "y": max(0.0, t["y"] - 0.06),
            "w": min(0.3, t["w"] + 0.12),
            "h": min(0.3, t["h"] + 0.12),
            "points": [],
            "length_ft": None,
            "width_ft": None,
            "confidence": t["confidence"],
            "extra": {},
        })
        room_list.append({
            "name": t["text"],
            "area_sqft": None,
            "is_bathroom": t["is_bathroom"],
        })
        if t["is_bathroom"]:
            bath_count += 1

    detected_objects = wall_objs + door_objs + window_objs + room_objs

    # Confidence: baseline 45 + bonus if OCR + walls both fired
    conf = 45
    if wall_objs:
        conf += 10
    if room_objs:
        conf += 10
    if door_objs:
        conf += 5

    return {
        # Lengths unknown until calibration — expose zeros so the user knows
        # to click Calibrate Scale (banner will trigger in the UI).
        "wall_length": 0,
        "external_wall": 0,
        "internal_wall": 0,
        "rooms": len(room_list),
        "bathrooms": bath_count,
        "doors": len(door_objs),
        "windows": len(window_objs),
        "built_up_area_sqft": None,
        "confidence": conf,
        "scale_detected": False,
        "scale_note": ("Heuristic mode — run Calibrate scale to convert "
                       "pixel measurements to feet."),
        "approximate": True,
        "room_list": room_list,
        "detected_objects": detected_objects,
    }
