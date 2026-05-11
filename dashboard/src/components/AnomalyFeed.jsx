// src/components/AnomalyFeed.jsx
import { formatDistanceToNow } from "date-fns";

const SEVERITY_COLOR = {
  critical: "#FF4444",
  high:     "#FF6B35",
  medium:   "#FFB800",
  low:      "#7B61FF",
  normal:   "#00FFB2",
};

const SEVERITY_ICON = {
  critical: "🔴",
  high:     "🟠",
  medium:   "🟡",
  low:      "🔵",
  normal:   "🟢",
};

function AnomalyCard({ anomaly, isSelected, onClick }) {
  const color = SEVERITY_COLOR[anomaly.severity] || "#5A7A94";
  const icon  = SEVERITY_ICON[anomaly.severity]  || "⚪";

  const timeAgo = anomaly.triggered_at
    ? formatDistanceToNow(new Date(anomaly.triggered_at), { addSuffix: true })
    : "unknown";

  return (
    <div
      onClick={onClick}
      style={{
        padding:      "12px 16px",
        borderBottom: "1px solid #1A2332",
        cursor:       "pointer",
        background:   isSelected ? "#1A2F4A" : "transparent",
        borderLeft:   isSelected ? `3px solid ${color}` : "3px solid transparent",
        transition:   "all 0.15s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span>{icon}</span>
          <span style={{
            fontFamily:  "monospace",
            fontSize:    "12px",
            color:       "#F0F4F8",
            fontWeight:  "600",
          }}>
            {anomaly.metric_name?.replace(/_/g, " ")}
          </span>
        </div>
        <span style={{
          fontFamily:    "monospace",
          fontSize:      "10px",
          color,
          letterSpacing: "1px",
          fontWeight:    "700",
        }}>
          {anomaly.severity?.toUpperCase()}
        </span>
      </div>

      <div style={{
        display:       "flex",
        justifyContent: "space-between",
        marginTop:     "6px",
      }}>
        <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#5A7A94" }}>
          score: {Number(anomaly.anomaly_score).toFixed(3)}
        </span>
        <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#3A5A74" }}>
          {timeAgo}
        </span>
      </div>

      {anomaly.narrative && (
        <div style={{
          marginTop:  "6px",
          fontSize:   "11px",
          color:      "#7A9AB5",
          lineHeight: "1.5",
          overflow:   "hidden",
          display:    "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
        }}>
          {anomaly.narrative}
        </div>
      )}
    </div>
  );
}

export function AnomalyFeed({ anomalies, loading, selectedId, onSelect }) {
  if (loading) {
    return (
      <div style={{ padding: "32px", textAlign: "center",
                    color: "#3A5A74", fontFamily: "monospace", fontSize: "12px" }}>
        LOADING ANOMALIES...
      </div>
    );
  }

  if (!anomalies.length) {
    return (
      <div style={{ padding: "32px", textAlign: "center",
                    color: "#3A5A74", fontFamily: "monospace", fontSize: "12px" }}>
        NO ANOMALIES DETECTED
      </div>
    );
  }

  return (
    <div style={{ overflowY: "auto", flex: 1 }}>
      {anomalies.map((a) => (
        <AnomalyCard
          key={a.id}
          anomaly={a}
          isSelected={a.id === selectedId}
          onClick={() => onSelect(a)}
        />
      ))}
    </div>
  );
}