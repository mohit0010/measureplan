import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

if (!BACKEND_URL) {
  console.warn(
    "[PlanMeasure] REACT_APP_BACKEND_URL not set — API calls will use same-origin. " +
    "Set this env var in Vercel dashboard to your backend URL (e.g. https://your-backend.vercel.app)"
  );
}

export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_BASE });

export async function uploadPlan(file, onProgress, mode = "auto", model = "gemini-2.5-flash") {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/analyze", form, {
    headers: { "Content-Type": "multipart/form-data" },
    params: { mode, model },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    },
    timeout: 180000,
  });
  return res.data;
}

export async function getAnalysis(id) {
  const res = await api.get(`/analysis/${id}`);
  return res.data;
}

export async function getPageAnalysis(id, pageIndex) {
  const res = await api.get(`/analysis/${id}/pages/${pageIndex}`);
  return res.data;
}

export async function updateAnalysis(id, payload, pageIndex = 0) {
  const res = await api.put(`/analysis/${id}`, payload, {
    params: { page: pageIndex },
  });
  return res.data;
}

export async function calibrateAnalysis(id, p1, p2, knownFt, pageIndex = 0) {
  const res = await api.post(`/analysis/${id}/calibrate`, {
    p1,
    p2,
    known_ft: knownFt,
  }, { params: { page: pageIndex } });
  return res.data;
}

export async function listAnalyses() {
  const res = await api.get(`/analyses`);
  return res.data;
}

export async function deleteAnalysis(id) {
  const res = await api.delete(`/analysis/${id}`);
  return res.data;
}

export function previewUrl(id, pageIndex = null) {
  if (pageIndex !== null && pageIndex !== undefined) {
    return `${API_BASE}/analysis/${id}/pages/${pageIndex}/preview`;
  }
  return `${API_BASE}/analysis/${id}/preview`;
}

export function reportUrl(id) {
  return `${API_BASE}/analysis/${id}/report`;
}
