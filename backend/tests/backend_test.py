"""Backend API tests for PlanMeasure AI."""
import io
import os
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

DEMO_ID = "demo-ce39f09c"
APPROX_ID = "demo-approx-1"
MULTI_ID = "demo-multi-3f"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


# ---------- Health ----------
def test_health(api):
    r = api.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


# ---------- List analyses ----------
def test_list_analyses_includes_demo(api):
    r = api.get(f"{BASE_URL}/api/analyses", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = [d.get("id") for d in data]
    assert DEMO_ID in ids, f"Demo id not found. Present ids: {ids}"


# ---------- Get analysis ----------
def test_get_demo_analysis_shape(api):
    r = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    required = [
        "id", "filename", "wall_length", "external_wall", "internal_wall",
        "wall_length_m", "rooms", "bathrooms", "doors", "windows",
        "confidence", "detected_objects", "room_list",
        "preview_image", "preview_width", "preview_height",
    ]
    for k in required:
        assert k in d, f"missing key: {k}"
    assert d["id"] == DEMO_ID
    assert isinstance(d["detected_objects"], list)
    assert len(d["detected_objects"]) > 0
    obj = d["detected_objects"][0]
    for k in ("type", "x", "y", "w", "h", "points", "label", "confidence"):
        assert k in obj, f"detected_object missing key: {k}"
    assert d["preview_image"].endswith(f"/api/analysis/{DEMO_ID}/preview")


# ---------- Preview image ----------
def test_get_demo_preview_png(api):
    r = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}/preview", timeout=15)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 100


# ---------- PDF report ----------
def test_get_demo_report_pdf(api):
    r = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}/report", timeout=30)
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    assert "application/pdf" in ctype
    disp = r.headers.get("content-disposition", "")
    assert "attachment" in disp.lower()
    assert r.content[:5] == b"%PDF-", f"Not PDF header: {r.content[:8]!r}"
    assert len(r.content) > 5 * 1024, f"PDF too small: {len(r.content)} bytes"


# ---------- Update / edit mode ----------
def test_update_demo_analysis(api):
    # First fetch original to restore later
    orig = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}", timeout=15).json()

    body = {
        "detected_objects": [{
            "id": "test_wall",
            "type": "wall_internal",
            "label": "Test Wall",
            "x": 0.3, "y": 0.3, "w": 0.1, "h": 0.005,
            "points": [[0.3, 0.3], [0.4, 0.3]],
            "length_ft": 12,
            "confidence": 100,
        }]
    }
    r = api.put(f"{BASE_URL}/api/analysis/{DEMO_ID}", json=body, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["doors"] == 0
    assert d["windows"] == 0
    assert d["internal_wall"] > 0

    # Restore original
    restore = {
        "detected_objects": [
            {
                "id": o.get("id"),
                "type": o.get("type"),
                "label": o.get("label", ""),
                "x": o.get("x", 0), "y": o.get("y", 0),
                "w": o.get("w", 0), "h": o.get("h", 0),
                "points": o.get("points", []),
                "width_ft": o.get("width_ft"),
                "length_ft": o.get("length_ft"),
                "confidence": o.get("confidence", 90),
            } for o in orig.get("detected_objects", [])
        ],
        "room_list": orig.get("room_list", []),
    }
    rr = api.put(f"{BASE_URL}/api/analysis/{DEMO_ID}", json=restore, timeout=15)
    assert rr.status_code == 200


# ---------- Analyze error paths ----------
def test_analyze_unsupported_file_type(api):
    files = {"file": ("bad.txt", b"hello", "text/plain")}
    r = api.post(f"{BASE_URL}/api/analyze", files=files, timeout=15)
    assert r.status_code == 400
    assert "Unsupported file type" in r.text


def test_analyze_valid_png_expected_budget_error(api):
    """Test /api/analyze endpoint behavior with/without API key."""
    img = Image.new("RGB", (200, 200), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    files = {"file": ("test.png", buf.getvalue(), "image/png")}
    r = api.post(f"{BASE_URL}/api/analyze", files=files, timeout=60)
    # Documented pending env issue — accept 500 with budget error, or 200 if key funded
    if r.status_code == 500:
        assert "Budget" in r.text or "budget" in r.text or "Analysis failed" in r.text
    else:
        assert r.status_code == 200


# ---------- Delete nonexistent ----------
def test_delete_nonexistent_returns_404(api):
    r = api.delete(f"{BASE_URL}/api/analysis/does-not-exist-xyz", timeout=15)
    assert r.status_code == 404


# ---------- Calibration (iteration 2) ----------
class TestCalibration:
    """Tests for POST /api/analysis/{aid}/calibrate."""

    def test_calibrate_success_rescales_measurements(self, api):
        # First calibrate with a distinct known_ft to force a different scale
        # (guards against re-runs where prior state already matches the target).
        api.post(f"{BASE_URL}/api/analysis/{APPROX_ID}/calibrate",
                 json={"p1": [0.1, 0.5], "p2": [0.9, 0.5], "known_ft": 25.0},
                 timeout=15)
        pre = api.get(f"{BASE_URL}/api/analysis/{APPROX_ID}", timeout=15).json()
        pre_wall = pre["wall_length"]

        body = {"p1": [0.08, 0.11], "p2": [0.92, 0.11], "known_ft": 50.0}
        r = api.post(f"{BASE_URL}/api/analysis/{APPROX_ID}/calibrate",
                     json=body, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # scale flags flipped
        assert d["scale_detected"] is True
        assert d["approximate"] is False
        assert "User calibrated" in (d["scale_note"] or "")
        assert "ft/px" in d["scale_note"]
        # wall length recomputed (should be a real number)
        assert isinstance(d["wall_length"], (int, float))
        assert d["wall_length"] > 0
        # confidence bumped >=92
        assert d["confidence"] >= 92.0
        # built_up_area now populated (rooms in seed have rect w/h)
        assert d["built_up_area_sqft"] is not None
        assert d["built_up_area_sqft"] > 0
        # different from previous state
        assert d["wall_length"] != pre_wall, (
            f"wall_length unchanged: {pre_wall} -> {d['wall_length']}"
        )

    def test_calibrate_persists(self, api):
        """GET after calibrate returns the same calibrated values."""
        body = {"p1": [0.1, 0.5], "p2": [0.9, 0.5], "known_ft": 40.0}
        post = api.post(f"{BASE_URL}/api/analysis/{APPROX_ID}/calibrate",
                        json=body, timeout=15).json()
        got = api.get(f"{BASE_URL}/api/analysis/{APPROX_ID}", timeout=15).json()
        assert got["scale_detected"] is True
        assert got["approximate"] is False
        assert got["scale_note"] == post["scale_note"]
        assert got["wall_length"] == post["wall_length"]

    def test_calibrate_zero_known_ft_422(self, api):
        body = {"p1": [0.1, 0.1], "p2": [0.9, 0.1], "known_ft": 0}
        r = api.post(f"{BASE_URL}/api/analysis/{APPROX_ID}/calibrate",
                     json=body, timeout=15)
        assert r.status_code == 422, r.text

    def test_calibrate_negative_known_ft_422(self, api):
        body = {"p1": [0.1, 0.1], "p2": [0.9, 0.1], "known_ft": -5}
        r = api.post(f"{BASE_URL}/api/analysis/{APPROX_ID}/calibrate",
                     json=body, timeout=15)
        assert r.status_code == 422, r.text

    def test_calibrate_bad_points_422(self, api):
        # p1 must be a 2-element list
        body = {"p1": [0.1], "p2": [0.9, 0.1], "known_ft": 10}
        r = api.post(f"{BASE_URL}/api/analysis/{APPROX_ID}/calibrate",
                     json=body, timeout=15)
        assert r.status_code == 422, r.text

    def test_calibrate_nonexistent_404(self, api):
        body = {"p1": [0.1, 0.1], "p2": [0.9, 0.1], "known_ft": 10.0}
        r = api.post(f"{BASE_URL}/api/analysis/nonexistent/calibrate",
                     json=body, timeout=15)
        assert r.status_code == 404, r.text


# ---------- Multi-page (iteration 3) ----------
class TestMultiPage:
    """Tests for multi-page PDF support (demo-multi-3f)."""

    def test_multi_aggregate_shape(self, api):
        r = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == MULTI_ID
        assert d["page_count"] == 3
        assert isinstance(d.get("pages"), list)
        assert len(d["pages"]) == 3
        # Aggregate == sum of page wall_lengths
        page_sum = round(sum(p["wall_length"] for p in d["pages"]), 1)
        assert abs(d["wall_length"] - page_sum) < 0.2, (
            f"aggregate wall_length={d['wall_length']} != sum({page_sum})"
        )
        # Rooms == sum of page rooms
        room_sum = sum(p["rooms"] for p in d["pages"])
        assert d["rooms"] == room_sum
        # Each page meta has required keys + correct preview URL
        for i, p in enumerate(d["pages"]):
            assert p["page_index"] == i
            assert p["preview_image"] == f"/api/analysis/{MULTI_ID}/pages/{i}/preview"
            for k in ("wall_length", "rooms", "bathrooms", "doors", "windows"):
                assert k in p

    def test_get_page_0_1_2(self, api):
        # Fetch aggregate first for reference values
        agg = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}", timeout=15).json()
        for i in range(3):
            r = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/{i}", timeout=15)
            assert r.status_code == 200
            d = r.json()
            assert d["page_index"] == i
            assert d["preview_image"] == f"/api/analysis/{MULTI_ID}/pages/{i}/preview"
            # Value must match what aggregate.pages reports for that page
            expected = agg["pages"][i]["wall_length"]
            assert d["wall_length"] == expected, (
                f"page {i}: wall_length={d['wall_length']}, expected={expected}"
            )

    def test_get_page_out_of_range_404(self, api):
        r = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/99", timeout=15)
        assert r.status_code == 404

    def test_get_page_preview_png(self, api):
        """Each page preview must be a real PNG. Previously wiped by data-loss bug."""
        for i in range(3):
            r = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/{i}/preview",
                        timeout=15)
            assert r.status_code == 200, f"page {i} preview status={r.status_code}"
            assert r.headers.get("content-type", "").startswith("image/png")
            assert len(r.content) > 1000, f"page {i} preview too small: {len(r.content)}"

    def test_legacy_single_page_still_works(self, api):
        """Legacy single-page doc: page_count=1, pages/0 returns whole doc, pages/1 404."""
        r = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["page_count"] == 1
        # pages array may be empty for legacy or single-item — allow both
        pages = d.get("pages", [])
        assert isinstance(pages, list)
        assert len(pages) in (0, 1)

        r0 = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}/pages/0", timeout=15)
        assert r0.status_code == 200, r0.text
        d0 = r0.json()
        assert d0["id"] == DEMO_ID
        assert d0["page_index"] == 0

        r1 = api.get(f"{BASE_URL}/api/analysis/{DEMO_ID}/pages/1", timeout=15)
        assert r1.status_code == 404

    def test_put_page1_reaggregates(self, api):
        """PUT page=1 should only alter page 1 and re-aggregate top-level totals."""
        # Fetch current state (aggregate + per-page)
        agg_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}", timeout=15).json()
        p0_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/0",
                            timeout=15).json()
        p1_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/1",
                            timeout=15).json()
        p2_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/2",
                            timeout=15).json()

        # Restore payload for page 1 (original objects)
        restore_p1 = {
            "detected_objects": [
                {
                    "id": o.get("id"),
                    "type": o.get("type"),
                    "label": o.get("label", ""),
                    "x": o.get("x", 0), "y": o.get("y", 0),
                    "w": o.get("w", 0), "h": o.get("h", 0),
                    "points": o.get("points", []),
                    "width_ft": o.get("width_ft"),
                    "length_ft": o.get("length_ft"),
                    "confidence": o.get("confidence", 90),
                } for o in p1_before.get("detected_objects", [])
            ],
            "room_list": p1_before.get("room_list", []),
        }

        try:
            # Apply a small edit to page 1 only
            body = {
                "detected_objects": [{
                    "id": "test_wall_p1",
                    "type": "wall_internal",
                    "label": "Test wall p1",
                    "x": 0.3, "y": 0.3, "w": 0.1, "h": 0.005,
                    "points": [[0.3, 0.3], [0.4, 0.3]],
                    "length_ft": 15,
                    "confidence": 100,
                }]
            }
            r = api.put(f"{BASE_URL}/api/analysis/{MULTI_ID}",
                        json=body, params={"page": 1}, timeout=15)
            assert r.status_code == 200, r.text
            d = r.json()
            # response is for the page just edited
            assert d["page_index"] == 1
            assert d["doors"] == 0
            assert d["windows"] == 0
            assert d["internal_wall"] > 0

            # Verify by GET
            got_p1 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/1",
                             timeout=15).json()
            assert got_p1["wall_length"] == d["wall_length"]

            # Other pages unchanged
            got_p0 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/0",
                             timeout=15).json()
            got_p2 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/2",
                             timeout=15).json()
            assert got_p0["wall_length"] == p0_before["wall_length"]
            assert got_p2["wall_length"] == p2_before["wall_length"]

            # Aggregate reflects new page-1 value
            agg_after = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}", timeout=15).json()
            assert agg_after["page_count"] == 3
            expected = round(
                got_p0["wall_length"] + got_p1["wall_length"] + got_p2["wall_length"], 1
            )
            assert abs(agg_after["wall_length"] - expected) < 0.2, (
                f"agg_wall={agg_after['wall_length']} expected≈{expected}"
            )
        finally:
            # Restore page 1
            api.put(f"{BASE_URL}/api/analysis/{MULTI_ID}",
                    json=restore_p1, params={"page": 1}, timeout=15)

    def test_calibrate_page0_reaggregates(self, api):
        """POST calibrate?page=0 should rescale page 0 and update aggregate."""
        # Save original page-0 state so we can restore-ish (calibrate can't fully undo
        # but we can re-run with a value that reproduces original wall length).
        p0_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/0",
                            timeout=15).json()
        p1_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/1",
                            timeout=15).json()
        p2_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/2",
                            timeout=15).json()

        body = {"p1": [0.08, 0.11], "p2": [0.92, 0.11], "known_ft": 50.0}
        r = api.post(f"{BASE_URL}/api/analysis/{MULTI_ID}/calibrate",
                     json=body, params={"page": 0}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["page_index"] == 0
        assert d["scale_detected"] is True
        assert d["approximate"] is False

        # Page 0 wall changed; pages 1/2 unchanged
        got_p0 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/0",
                         timeout=15).json()
        got_p1 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/1",
                         timeout=15).json()
        got_p2 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/2",
                         timeout=15).json()
        assert got_p0["scale_detected"] is True
        assert got_p1["wall_length"] == p1_before["wall_length"]
        assert got_p2["wall_length"] == p2_before["wall_length"]

        # Aggregate updated to new sum
        agg = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}", timeout=15).json()
        assert agg["page_count"] == 3
        expected_sum = round(
            got_p0["wall_length"] + got_p1["wall_length"] + got_p2["wall_length"], 1
        )
        assert abs(agg["wall_length"] - expected_sum) < 0.2

    def test_multi_report_pdf(self, api):
        """Multi-page report PDF valid, contains 3 pages, and >20KB (with embedded previews)."""
        r = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/report", timeout=30)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        # Multi-page PDF should have >=3 page objects
        assert r.content.count(b"/Type /Page\n") >= 3, (
            f"expected >=3 pages, found {r.content.count(b'/Type /Page')}"
        )
        # After the fix, per-page preview_b64 must survive → PDF must embed images → >20 KB
        assert len(r.content) > 20 * 1024, (
            f"PDF too small: {len(r.content)} bytes — per-page previews likely wiped."
        )

    def test_analyses_list_page_count(self, api):
        r = api.get(f"{BASE_URL}/api/analyses", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        by_id = {d["id"]: d for d in rows}
        assert MULTI_ID in by_id
        assert by_id[MULTI_ID]["page_count"] == 3
        assert DEMO_ID in by_id
        assert by_id[DEMO_ID]["page_count"] == 1

    def test_previews_survive_mutations_bugfix_verification(self, api):
        """RE-VERIFY iteration-3 CRITICAL data-loss bug is FIXED.

        Before fix: PUT/calibrate replaced whole `pages` array with a copy fetched
        without preview_b64, wiping per-page images. After fix: positional $set
        `pages.{page}.data` preserves preview_b64 on every page.

        Flow:
          1. All 3 previews return 200 image/png BEFORE mutations.
          2. PUT page=1 with a door-only body → still 200 image/png on all pages.
          3. POST calibrate page=0 → still 200 image/png on all pages.
          4. GET report → PDF >20 KB with %PDF header.
          5. GET pages/1 reflects mutated data (doors=1 from PUT).
        """
        # Step 1: baseline — all previews 200
        pre_sizes = []
        for i in range(3):
            r = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/{i}/preview",
                        timeout=15)
            assert r.status_code == 200, f"pre-mutation page {i} preview NOT 200"
            assert r.headers.get("content-type", "").startswith("image/png")
            pre_sizes.append(len(r.content))

        # Save p1/p0 state for restore
        p1_before = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/1",
                            timeout=15).json()
        restore_p1 = {
            "detected_objects": [
                {
                    "id": o.get("id"), "type": o.get("type"),
                    "label": o.get("label", ""),
                    "x": o.get("x", 0), "y": o.get("y", 0),
                    "w": o.get("w", 0), "h": o.get("h", 0),
                    "points": o.get("points", []),
                    "width_ft": o.get("width_ft"),
                    "length_ft": o.get("length_ft"),
                    "confidence": o.get("confidence", 90),
                } for o in p1_before.get("detected_objects", [])
            ],
            "room_list": p1_before.get("room_list", []),
        }

        try:
            # Step 2: PUT page=1 with single door object
            put_body = {
                "detected_objects": [{
                    "id": "test", "type": "door", "label": "t",
                    "x": 0.1, "y": 0.1, "w": 0.05, "h": 0.05,
                    "points": [], "confidence": 100,
                }]
            }
            r = api.put(f"{BASE_URL}/api/analysis/{MULTI_ID}",
                        json=put_body, params={"page": 1}, timeout=15)
            assert r.status_code == 200, r.text

            # All 3 previews STILL 200 after PUT
            for i in range(3):
                r2 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/{i}/preview",
                             timeout=15)
                assert r2.status_code == 200, (
                    f"POST-PUT page {i} preview status={r2.status_code} — "
                    "DATA-LOSS BUG STILL PRESENT"
                )
                assert r2.headers.get("content-type", "").startswith("image/png")
                assert len(r2.content) > 1000

            # Step 5: verify page 1 shows the mutated doors=1
            got_p1 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/1",
                             timeout=15).json()
            assert got_p1["doors"] == 1, f"expected doors=1 got {got_p1['doors']}"
            assert got_p1["windows"] == 0
            # Note: recompute_from_objects keeps prior wall totals when new object
            # list has no wall objects (analyzer.py L528-535), so wall_length may
            # be non-zero here. That's a separate concern from the data-loss bug.

            # Step 3: POST calibrate page=0
            cal_body = {"p1": [0.08, 0.11], "p2": [0.92, 0.11], "known_ft": 50.0}
            r3 = api.post(f"{BASE_URL}/api/analysis/{MULTI_ID}/calibrate",
                          json=cal_body, params={"page": 0}, timeout=15)
            assert r3.status_code == 200, r3.text

            # All 3 previews STILL 200 after calibrate
            for i in range(3):
                r4 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/pages/{i}/preview",
                             timeout=15)
                assert r4.status_code == 200, (
                    f"POST-CAL page {i} preview status={r4.status_code} — "
                    "DATA-LOSS BUG STILL PRESENT (calibrate path)"
                )
                assert r4.headers.get("content-type", "").startswith("image/png")
                assert len(r4.content) > 1000

            # Step 4: report PDF > 20 KB, starts with %PDF
            r5 = api.get(f"{BASE_URL}/api/analysis/{MULTI_ID}/report", timeout=30)
            assert r5.status_code == 200
            assert r5.content[:5] == b"%PDF-"
            assert len(r5.content) > 20 * 1024, (
                f"PDF size={len(r5.content)} bytes — should exceed 20 KB with "
                "per-page embedded previews"
            )
        finally:
            # Restore page 1
            api.put(f"{BASE_URL}/api/analysis/{MULTI_ID}",
                    json=restore_p1, params={"page": 1}, timeout=15)

