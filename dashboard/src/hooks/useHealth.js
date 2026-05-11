// src/hooks/useHealth.js
import { useState, useEffect } from "react";
import { api } from "../lib/api";

export function useHealth() {
  const [health,  setHealth]  = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetch() {
      try {
        const data = await api.getHealth();
        setHealth(data);
      } catch (e) {
        setHealth({ overall: "red", error: e.message });
      } finally {
        setLoading(false);
      }
    }
    fetch();
    const interval = setInterval(fetch, 30_000);
    return () => clearInterval(interval);
  }, []);

  return { health, loading };
}