// src/hooks/useMetrics.js
import { useState, useEffect } from "react";
import { api } from "../lib/api";

export function useMetrics() {
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    let interval;

    async function fetch() {
      try {
        const data = await api.getMetrics();
        setMetrics(data.metrics || []);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }

    fetch();
    // Refresh every 60 seconds
    interval = setInterval(fetch, 60_000);
    return () => clearInterval(interval);
  }, []);

  return { metrics, loading, error };
}