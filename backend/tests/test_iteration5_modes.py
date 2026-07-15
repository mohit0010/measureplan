"""Iteration 5: tests for `mode=auto|llm|heuristic` on /api/analyze.

Covers:
  - heuristic mode: floor-plan PNG returns 200 with expected shape
  - invalid mode → 400
  - auto mode: llm/heuristic behavioural fallback
  - llm mode: strict (no fallback)
  - heuristic on multi-page PDF
  - calibration on heuristic result
  - GET /api/analyses includes analysis_mode
"""
import io
import os
import pytest
import requests
from PIL import Image, ImageDraw

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


def _make_floorplan_png(w: int = 800, h: int = 600) -> bytes:
    """A moderately realistic floor plan for OpenCV detection.
    Internal walls kept strictly inside the 12% border margin so the
    heuristic classifier tags them as `wall_internal`.
    """
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    # Outer rectangle (external walls)
    d.rectangle([40, 40, w - 40, h - 40], outline="black", width=6)
    # Internal walls placed >12% from all borders
    inner_x1, inner_y1 = int(w * 0.20), int(h * 0.20)
    inner_x2, inner_y2 = int(w * 0.80), int(h * 0.80)
    # Vertical internal wall (mid, inset from borders)
    d.line([(w // 2, inner_y1), (w // 2, inner_y2)], fill="black", width=4)
    # Horizontal internal wall (left half, inset)
    d.line([(inner_x1, h // 2), (w // 2, h // 2)], fill="black", width=4)
    # Room labels — must match COMMON_ROOM_KEYWORDS in heuristic_analyzer
    d.text((120, 120), "Bedroom 1", fill="black")
    d.text((120, h // 2 + 40), "Kitchen", fill="black")
    d.text((w // 2 + 60, 120), "Living Room", fill="black")
    d.text((w // 2 + 60, h - 120), "Bathroom", fill="black")
    # Draw a door (circle-ish arc)
    d.arc([(w // 2 - 30, h // 2 - 30), (w // 2 + 30, h // 2 + 30)],
          0, 90, fill="black", width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_multi_pdf_bytes(pages: int = 2) -> bytes:
    """Two-page PDF built with PyMuPDF, embedding a floor plan PNG per page."""
    import fitz
    doc = fitz.open()
    for _ in range(pages):
        png = _make_floorplan_png(700, 500)
        img_doc = fitz.open("png", png)
        rect = fitz.Rect(0, 0, 700, 500)
        pdf_page = doc.new_page(width=700, height=500)
        pdf_page.insert_image(rect, stream=png)
        img_doc.close()
    out = doc.tobytes()
    doc.close()
    return out


# ---------- heuristic mode ----------
class TestHeuristicMode:
    def test_heuristic_png_returns_expected_shape(self, api):
        png = _make_floorplan_png()
        files = {"file": ("floorplan_test.png", png, "image/png")}
        r = api.post(f"{BASE_URL}/api/analyze", files=files,
                     params={"mode": "heuristic"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["analysis_mode"] == "heuristic"
        # heuristic reports pixel-only measurements until calibration
        assert d["wall_length"] == 0
        assert d["scale_detected"] is False
        assert "Heuristic mode" in (d["scale_note"] or "")
        assert d["approximate"] is True
        assert 45 <= d["confidence"] <= 90

        objs = d["detected_objects"]
        types = [o["type"] for o in objs]
        walls = [t for t in types if t.startswith("wall_")]
        rooms = [t for t in types if t in ("room", "bathroom")]
        assert len(walls) > 0, f"no walls detected, types={set(types)}"
        assert "wall_external" in types
        assert "wall_internal" in types
        assert len(rooms) >= 1, f"no rooms detected, types={set(types)}"

    def test_heuristic_result_is_calibratable(self, api):
        """Create a heuristic analysis, then calibrate — wall_length becomes non-zero."""
        png = _make_floorplan_png()
        files = {"file": ("calib_test.png", png, "image/png")}
        r = api.post(f"{BASE_URL}/api/analyze", files=files,
                     params={"mode": "heuristic"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        aid = d["id"]
        assert d["wall_length"] == 0

        # Calibrate against a long horizontal span across the outer wall
        cal = {"p1": [0.06, 0.08], "p2": [0.94, 0.08], "known_ft": 40.0}
        rc = api.post(f"{BASE_URL}/api/analysis/{aid}/calibrate",
                      json=cal, timeout=15)
        assert rc.status_code == 200, rc.text
        got = rc.json()
        assert got["scale_detected"] is True
        assert got["approximate"] is False
        assert got["wall_length"] > 0, (
            f"expected non-zero wall_length after calibration, got {got['wall_length']}"
        )
        # cleanup
        api.delete(f"{BASE_URL}/api/analysis/{aid}", timeout=15)

    def test_heuristic_multipage_pdf(self, api):
        pdf = _make_multi_pdf_bytes(pages=2)
        files = {"file": ("multi_test.pdf", pdf, "application/pdf")}
        r = api.post(f"{BASE_URL}/api/analyze", files=files,
                     params={"mode": "heuristic"}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["analysis_mode"] == "heuristic"
        assert d["page_count"] == 2, f"expected 2 pages, got {d['page_count']}"
        assert len(d.get("pages", [])) == 2
        # cleanup
        api.delete(f"{BASE_URL}/api/analysis/{d['id']}", timeout=15)


# ---------- invalid mode ----------
def test_invalid_mode_returns_400(api):
    png = _make_floorplan_png(200, 200)
    files = {"file": ("bad_mode.png", png, "image/png")}
    r = api.post(f"{BASE_URL}/api/analyze", files=files,
                 params={"mode": "invalid"}, timeout=30)
    assert r.status_code == 400
    assert "mode must be one of" in r.text


# ---------- auto mode ----------
class TestAutoMode:
    def test_auto_mode_returns_llm_or_heuristic(self, api):
        """Either LLM works (analysis_mode=llm) or auto falls back to heuristic
        with fallback_note. Both are correct per spec."""
        png = _make_floorplan_png()
        files = {"file": ("auto_test.png", png, "image/png")}
        r = api.post(f"{BASE_URL}/api/analyze", files=files,
                     params={"mode": "auto"}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["analysis_mode"] in ("llm", "heuristic")
        if d["analysis_mode"] == "llm":
            assert d["fallback_note"] == ""
        else:
            assert "LLM vision unavailable" in (d["fallback_note"] or ""), (
                f"unexpected fallback_note: {d.get('fallback_note')}"
            )
        # cleanup
        api.delete(f"{BASE_URL}/api/analysis/{d['id']}", timeout=15)


# ---------- llm strict mode ----------
class TestLlmMode:
    def test_llm_mode_strict_no_fallback(self, api):
        """mode=llm should succeed with analysis_mode='llm' or fail with 402/503/500,
        never silently produce analysis_mode='heuristic'."""
        png = _make_floorplan_png()
        files = {"file": ("llm_test.png", png, "image/png")}
        r = api.post(f"{BASE_URL}/api/analyze", files=files,
                     params={"mode": "llm"}, timeout=120)
        if r.status_code == 200:
            d = r.json()
            assert d["analysis_mode"] == "llm", (
                f"mode=llm returned analysis_mode={d.get('analysis_mode')} — "
                "STRICT MODE VIOLATION"
            )
            api.delete(f"{BASE_URL}/api/analysis/{d['id']}", timeout=15)
        else:
            # Budget/quota → 402, unconfigured → 503, other → 500
            assert r.status_code in (402, 500, 503), (
                f"unexpected status {r.status_code}: {r.text[:200]}"
            )


# ---------- /api/analyses summary shape ----------
def test_analyses_list_includes_analysis_mode(api):
    r = api.get(f"{BASE_URL}/api/analyses", timeout=15)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) > 0
    for row in rows:
        assert "analysis_mode" in row, (
            f"row missing analysis_mode: {list(row.keys())}"
        )
        assert row["analysis_mode"] in ("llm", "heuristic")
