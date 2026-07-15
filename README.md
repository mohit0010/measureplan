# PlanMeasure AI

AI-powered floor plan analyzer that extracts wall lengths, room counts, door/window counts, and built-up areas from uploaded floor plans (PDF, PNG, JPG).

## Features

- **AI Vision Analysis**: Uses Google Gemini (2.5 Flash, 2.0 Flash) for intelligent floor plan reading
- **Local Fallback**: OpenCV + Tesseract pipeline for fully offline analysis
- **Multi-page PDF Support**: Analyzes every page of a PDF document
- **Interactive Plan Viewer**: SVG overlays with zoom/pan, layer toggles, hover tooltips
- **Manual Correction**: Edit mode to add/delete/relabel walls, doors, windows
- **Scale Calibration**: User-drawn segment calibration for precise measurements
- **PDF Report**: Professional report with preview, metrics, and room list
- **Light/Dark Mode**: Full theme support

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + React Router + Tailwind + shadcn/ui + Framer Motion |
| Backend | FastAPI + MongoDB (motor) |
| AI Vision | Google Gemini (free tier via `google-generativeai`) |
| CV/PDF | OpenCV, PyMuPDF, Pillow |
| OCR | Tesseract |
| Reports | ReportLab |

## Project Structure

```
├── frontend/          # React frontend (separate Vercel project)
│   ├── src/
│   ├── public/
│   ├── vercel.json
│   └── package.json
├── backend/           # FastAPI backend (separate Vercel project)
│   ├── api/           # Vercel serverless entry point
│   ├── analyzer.py    # AI vision + building data extraction
│   ├── heuristic_analyzer.py  # OpenCV/Tesseract fallback
│   ├── server.py      # FastAPI endpoints
│   ├── pdf_report.py  # ReportLab PDF generator
│   ├── requirements.txt
│   └── vercel.json
└── memory/
    └── PRD.md
```

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- MongoDB (local or Atlas free tier)
- Tesseract OCR (for local heuristic mode)

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your values:
#   GOOGLE_API_KEY=your-key (get free from https://aistudio.google.com/apikey)
#   MONGO_URL=mongodb://localhost:27017
#   DB_NAME=planmeasure
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

### Frontend

```bash
cd frontend
cp .env.example .env
# Edit .env: REACT_APP_BACKEND_URL=http://localhost:8000
yarn install
yarn start
```

## Deployment (Vercel — Free)

### Backend

1. Push `backend/` to a Git repository
2. Import in Vercel → select the `backend` directory
3. Set environment variables in Vercel dashboard:
   - `GOOGLE_API_KEY` — your free Gemini API key
   - `MONGO_URL` — MongoDB Atlas connection string (free tier)
   - `DB_NAME` — `planmeasure`
4. Deploy — Vercel auto-detects `vercel.json` + Python

### Frontend

1. Push `frontend/` to a Git repository
2. Import in Vercel → select the `frontend` directory
3. Set environment variables:
   - `REACT_APP_BACKEND_URL` — your deployed backend URL
4. Build command: `yarn build`
5. Output directory: `build`

## Available AI Models (All Free)

| Model | ID | Notes |
|-------|---|-------|
| Gemini 2.5 Flash | `gemini-2.5-flash` | Best accuracy, recommended |
| Gemini 2.5 Flash Lite | `gemini-2.5-flash-lite` | Faster, lower token usage |
| Gemini 2.0 Flash | `gemini-2.0-flash` | Legacy fallback |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze` | Upload plan + analyze (`?mode=auto\|llm\|heuristic&model=gemini-2.5-flash`) |
| `GET` | `/api/analysis/{id}` | Get analysis result |
| `PUT` | `/api/analysis/{id}` | Manual corrections |
| `GET` | `/api/analysis/{id}/preview` | Preview image |
| `GET` | `/api/analysis/{id}/report` | PDF report |
| `POST` | `/api/analysis/{id}/calibrate` | Scale calibration |
| `GET` | `/api/analyses` | List history |
| `DELETE` | `/api/analysis/{id}` | Delete analysis |
| `GET` | `/api/models` | List available AI models |