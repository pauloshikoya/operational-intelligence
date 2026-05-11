// src/hooks/useAnomalies.js
import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";

export function useAnomalies(filters = {}) {
  const [anomalies, setAnomalies] = useState([]);
  const [pagination, setPagination] = useState({});
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  const fetch = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getAnomalies(filters);
      setAnomalies(data.anomalies);
      setPagination(data.pagination);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => { fetch(); }, [fetch]);

  // Prepend a new anomaly to the top of the list
  const addAnomaly = useCallback((anomaly) => {
    setAnomalies((prev) => {
      // Avoid duplicates
      if (prev.find((a) => a.id === anomaly.id)) return prev;
      return [anomaly, ...prev].slice(0, 50);
    });
  }, []);

  return { anomalies, pagination, loading, error, refetch: fetch, addAnomaly };
}