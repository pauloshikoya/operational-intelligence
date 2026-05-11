// src/lib/api.js

const BASE_URL = import.meta.env.VITE_API_URL || "http://172.23.39.230:8000";
const API_KEY  = import.meta.env.VITE_API_KEY  || "dev-key-change-in-production";

const headers = {
  "X-Api-Key":   API_KEY,
  "Content-Type": "application/json",
};

// ── Core fetch wrapper ─────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

// ── Endpoints ──────────────────────────────────────────────────────────────

export const api = {
  getHealth: () =>
    apiFetch("/health"),

  getAnomalies: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return apiFetch(`/anomalies${q ? "?" + q : ""}`);
  },

  getAnomaly: (id) =>
    apiFetch(`/anomalies/${id}`),

  getMetrics: () =>
    apiFetch("/metrics"),

  getMetricSeries: (name, hours = 168) =>
    apiFetch(`/metrics/${name}/series?hours=${hours}`),

  ask: (question, hours = 24) =>
    apiFetch("/ask", {
      method: "POST",
      body:   JSON.stringify({ question, hours }),
    }),
};

// ── SSE stream connection ──────────────────────────────────────────────────

export function connectStream(onAnomaly, onError) {
  const url = `${BASE_URL}/stream`;
  const es  = new EventSource(url);

  es.addEventListener("anomaly", (e) => {
    try {
      onAnomaly(JSON.parse(e.data));
    } catch (err) {
      console.error("Failed to parse anomaly event:", err);
    }
  });

  es.addEventListener("error", (e) => {
    console.error("SSE error:", e);
    onError?.(e);
  });

  return () => es.close();   // return cleanup function
}