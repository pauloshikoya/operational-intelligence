// src/components/StatsBar.jsx
import { useHealth } from "../hooks/useHealth";

function Stat({ label, value, color = "#F0F4F8" }) {
  return (
    <div style={{
      background:   "#0D1520",
      border:       "1px solid #1A2332",
      borderRadius: "6px",
      padding:      "16px 24px",
      flex:         1,
    }}>
      <div style={{
        fontFamily:    "monospace",
        fontSize:      "10px",
        color:         "#5A7A94",
        letterSpacing: "2px",
        marginBottom:  "8px",
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "monospace",
        fontSize:   "24px",
        fontWeight: "700",
        color,
      }}>
        {value ?? "—"}
      </div>
    </div>
  );
}

export function StatsBar() {
  const { health } = useHealth();
  const stats      = health?.pipeline_24h;
  const anomalies  = stats?.anomalies || {};

  const narrated = anomalies.narrated ?? 0;
  const total    = anomalies.total    ?? 0;

  return (
    <div style={{ display: "flex", gap: "12px", padding: "16px 32px" }}>
      <Stat
        label="DATA SOURCES"
        value={
          Object.keys(health?.data_sources || {}).length
        }
      />
      <Stat
        label="ANOMALIES 24H"
        value={total}
        color={total > 0 ? "#FF6B35" : "#00FFB2"}
      />
      <Stat
        label="CRITICAL / HIGH"
        value={`${anomalies.critical ?? 0} / ${anomalies.high ?? 0}`}
        color={
          (anomalies.critical ?? 0) > 0 ? "#FF4444" :
          (anomalies.high     ?? 0) > 0 ? "#FF6B35" : "#00FFB2"
        }
      />
      <Stat
        label="AI NARRATED"
        value={`${narrated} / ${total}`}
        color="#7B61FF"
      />
    </div>
  );
}