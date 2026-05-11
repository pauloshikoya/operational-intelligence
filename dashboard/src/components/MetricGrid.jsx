// src/components/MetricGrid.jsx
import { useMetrics } from "../hooks/useMetrics";

function MetricRow({ metric }) {
  const z   = parseFloat(metric.z_score || 0);
  const d1  = parseFloat(metric.pct_change_1d || 0);

  const statusColor =
    Math.abs(z) >= 3 ? "#FF4444" :
    Math.abs(z) >= 2 ? "#FF6B35" :
    Math.abs(z) >= 1 ? "#FFB800" : "#00FFB2";

  const statusIcon =
    Math.abs(z) >= 3 ? "🔴" :
    Math.abs(z) >= 2 ? "🟠" :
    Math.abs(z) >= 1 ? "🟡" : "🟢";

  return (
    <div style={{
      display:      "flex",
      alignItems:   "center",
      padding:      "8px 16px",
      borderBottom: "1px solid #1A2332",
      gap:          "8px",
    }}>
      <span style={{ fontSize: "12px" }}>{statusIcon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily:  "monospace",
          fontSize:    "11px",
          color:       "#D0E4F4",
          overflow:    "hidden",
          textOverflow:"ellipsis",
          whiteSpace:  "nowrap",
        }}>
          {metric.metric_name?.replace(/_/g, " ")}
        </div>
      </div>
      <div style={{ display: "flex", gap: "12px", flexShrink: 0 }}>
        <span style={{
          fontFamily: "monospace",
          fontSize:   "11px",
          color:      statusColor,
        }}>
          z={z >= 0 ? "+" : ""}{z.toFixed(2)}
        </span>
        <span style={{
          fontFamily: "monospace",
          fontSize:   "11px",
          color:      d1 >= 0 ? "#00FFB2" : "#FF6B35",
        }}>
          {d1 >= 0 ? "↑" : "↓"}{Math.abs(d1).toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

export function MetricGrid() {
  const { metrics, loading } = useMetrics();

  const sorted = [...metrics].sort(
    (a, b) => Math.abs(b.z_score || 0) - Math.abs(a.z_score || 0)
  );

  return (
    <div style={{ overflowY: "auto", flex: 1 }}>
      <div style={{
        padding:       "10px 16px",
        fontFamily:    "monospace",
        fontSize:      "10px",
        color:         "#5A7A94",
        letterSpacing: "2px",
        borderBottom:  "1px solid #1A2332",
      }}>
        METRIC HEALTH · SORTED BY Z-SCORE
      </div>
      {loading && (
        <div style={{ padding: "24px", color: "#3A5A74",
                      fontFamily: "monospace", fontSize: "11px" }}>
          LOADING METRICS...
        </div>
      )}
      {sorted.map((m, i) => (
        <MetricRow key={`${m.source}-${m.metric_name}-${i}`} metric={m} />
      ))}
    </div>
  );
}