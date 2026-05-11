// src/hooks/useStream.js
import { useEffect } from "react";
import { connectStream } from "../lib/api";

export function useStream(onAnomaly) {
  useEffect(() => {
    const disconnect = connectStream(onAnomaly, (err) => {
      console.warn("Stream error — will reconnect:", err);
    });
    return disconnect;
  }, []);
}