# PlanMeasure AI — PRD

## Original problem statement
Build a full-stack AI web application called "PlanMeasure AI" that accepts a
residential/commercial floor plan (PDF, JPG, PNG) upload and produces:
Total Wall Length (ft & m), External/Internal Wall Length, Room count,
Bathroom count, Door count, Window count, Built-up Area (if detectable),
AI Confidence Score. Includes an interactive plan viewer with SVG overlays
(walls=blue, doors=green, windows=orange, bathrooms=purple, rooms=gray),
manual correction / edit mode, PDF report download, and a modular architecture
that lets future modules (BOQ, Brick, Paint, Plaster, Cost Estimator) reuse
the same extracted building data.

## Stack
- Frontend: React (CRA) + React Router + Framer Motion + Tailwind + shadcn/ui + sonner
- Backend: FastAPI + MongoDB (motor)
- CV/PDF: OpenCV (headless), PyMuPDF, Pillow
- LLM Vision: Gemini (2.5 Flash / 2.0 Flash) via google-generativeai + GOOGLE_API_KEY (free tier)
- Report: ReportLab
- Fonts: Cabinet Grotesk (display) + IBM Plex Sans/Mono (body/data)

## Architecture
- `backend/analyzer.py` — modular `BuildingData` dataclass shared across
  future modules (BOQ, Brick, Paint, Cost). Pipeline: bytes -> PNG preview
      -> OpenCV wall-hint pre-pass -> Gemini structured JSON extraction
  -> `BuildingData`.
- `backend/pdf_report.py` — ReportLab PDF generator consuming `BuildingData`.
- `backend/server.py` — FastAPI endpoints under `/api/*`.
  - POST `/api/analyze` (multipart file)
  - GET `/api/analysis/{id}`
  - PUT `/api/analysis/{id}` (manual corrections, triggers recompute)
  - GET `/api/analysis/{id}/preview` (PNG)
  - GET `/api/analysis/{id}/report` (PDF)
  - GET `/api/analyses` (history)
  - DELETE `/api/analysis/{id}`

## User personas
- Estimator / Quantity Surveyor: quick QTO baseline from unstructured plans.
- Architect / Interior Designer: sanity-check room + opening counts.
- Contractor: pre-bid summary + shareable PDF report.

## Core requirements (static)
- Support PDF, PNG, JPG (≤20 MB). Convert PDF pages to high-res PNG.
- Detect walls (external / internal), doors, windows, rooms, bathrooms.
- Read dimensions and infer scale where possible.
- Return normalized bounding boxes + polylines for SVG overlays.
- Always return confidence + approximate flag.
- Interactive plan viewer with zoom/pan/hover tooltips + layer toggles.
- Manual correction: add / delete / relabel walls, doors, windows.
- PDF report with preview, metrics, and room list.
- Light + Dark mode.

## Implemented
### Iteration 1 (2026-02-13)
- [x] Full backend pipeline with modular BuildingData model.
- [x] Gemini 3 Flash vision integration for structured extraction.
- [x] Homepage with hero + upload dropzone (drag & drop, progress, validation).
- [x] Analysis page with SVG plan viewer, layer toggles, zoom/pan, hover
      tooltips, selection panel.
- [x] Stat card grid: total/ext/int walls (ft+m), rooms, baths, doors,
      windows, built-up area, confidence.
- [x] Manual correction toolbar (add/delete wall/door/window, save recompute).
- [x] History page + delete flow.
- [x] Professional PDF report (ReportLab) with preview + metrics + room list.
- [x] Light/Dark themes with Cabinet Grotesk + IBM Plex.
- [x] `data-testid` on all interactive/critical elements.

### Iteration 2 (2026-02-13)
- [x] **Scale calibration**: `POST /api/analysis/{id}/calibrate` endpoint —
      user draws a two-point segment on the plan viewer and enters its known
      length in feet; backend rescales every wall polyline (length_ft),
      door/window (width_ft), and computes built-up area. Sets
      `scale_detected=true`, `approximate=false`.
- [x] **Move/resize in Edit Mode**: 4 corner resize handles on rects + wall
      polyline endpoint handles. Motion clamped to [0,1].
- [x] Amber "No scale detected" banner surfaces a **Calibrate now** CTA.
- [x] Calibrate + Edit modes are mutually exclusive.
- [x] Friendly 402 error message when LLM budget is exhausted.

### Iteration 3 (2026-02-13)
- [x] **Multi-page PDF support**: `POST /api/analyze` now uses
      `analyze_document` — every PDF page (up to 8) is converted, analyzed
      independently via Gemini vision, and stored as `pages: [{page_index,
      preview_b64, data}]`. Top-level `data` becomes an aggregate summary.
- [x] New endpoints: `GET /api/analysis/{id}/pages/{n}` and
      `/pages/{n}/preview` for per-page drill-down.
- [x] `PUT /api/analysis/{id}` and `POST /api/analysis/{id}/calibrate` now
      accept a `?page=N` query param. Positional Mongo `$set: pages.{N}.data`
      preserves other pages' preview_b64 (critical bug caught + fixed in
      iteration_3 → iteration_4 regression cycle).
- [x] PDF report renders aggregate + per-page breakdown (image + stat table)
      when the doc has multiple pages.
- [x] Frontend page-selector strip appears when `page_count > 1`; each tab
      loads its own preview + detected_objects + rooms; stat cards switch to
      "Building totals · N pages" showing aggregate.
- [x] History page shows a "{n} pages" pill next to multi-page rows.

### Iteration 4 — Option A: LLM-free fallback (2026-02-14)
- [x] **Heuristic analyzer** (`backend/heuristic_analyzer.py`): pure OpenCV +
      Tesseract pipeline. Hough line detection for walls (classified
      external vs internal by border proximity), HoughCircles for door
      swings, Tesseract PSM 12 OCR for room labels with a bathroom keyword
      list. Emits same `BuildingData` shape as the LLM path — every
      downstream feature (calibration, edit mode, PDF report, multi-page)
      works unchanged.
- [x] `POST /api/analyze` accepts `?mode=auto|llm|heuristic`.
      - `llm`: strict (fails on quota).
      - `heuristic`: LLM-free (fully offline).
      - `auto`: try LLM, gracefully fall back on ANY exception with a
        friendly `fallback_note`.
- [x] Response + history now include `analysis_mode` field.
- [x] Frontend: 3-chip mode selector on the upload dropzone (Auto/AI
      Vision/Local) with dynamic hint text and mode-aware progress label.
- [x] Analysis page shows a `Local · LLM-free` or `AI Vision · Gemini 3`
      badge next to the Approximate/Measured badge.
- [x] Tesseract 5.3.0 + `pytesseract` added to backend deps.

## Setup
- Set `GOOGLE_API_KEY` in `backend/.env` — get a free key from
  https://aistudio.google.com/apikey (free tier includes generous quotas).
- Set `MONGO_URL` and `DB_NAME` in `backend/.env`.
- Set `REACT_APP_BACKEND_URL` in `frontend/.env` pointing to backend.
- Available free models: gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.0-flash.

## Backlog
- P1: Scale calibration prompt — allow user to draw a segment and enter a
      known length when scale is not detected.
- P1: Move / resize objects in Edit Mode (currently add + delete + rename).
- P1: Auth (JWT or Google) so history is per-user rather than global.
- P2: Batch upload / multi-page PDF (all pages).
- P2: Downstream modules — Brick Calc, BOQ, Paint Calc — consuming
      `BuildingData` (module scaffolding already isolated).
- P2: Diff view — compare original AI output vs manually corrected version.

## Next tasks
1. Deploy frontend and backend separately to Vercel.
2. Re-run testing agent with a real analysis.
3. Ship scale-calibration UI + move-object edit primitive.
