// src/components/Header.jsx
import { Activity } from "lucide-react";
import { useHealth } from "../hooks/useHealth";

export function Header() {
  const { health } = useHealth();
  const overall    = health?.overall || "amber";

  const statusColor = {
    green: "#00FFB2",
    amber: "#FFB800",
    red:   "#FF4444",
  }[overall] || "#FFB800";

  return (
    <header style={{
      background:   "#0D1520",
      borderBottom: "1px solid #1A2332",
      padding:      "16px 32px",
      display:      "flex",
      alignItems:   "center",
      justifyContent: "space-between",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <Activity size={20} color="#00FFB2" />
        <span style={{
          fontFamily:  "monospace",
          fontSize:    "14px",
          fontWeight:  "700",
          color:       "#F0F4F8",
          letterSpacing: "2px",
        }}>
          OPERATIONAL INTELLIGENCE
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <div style={{
          width:        "8px",
          height:       "8px",
          borderRadius: "50%",
          background:   statusColor,
          boxShadow:    `0 0 6px ${statusColor}`,
          animation:    "pulse 2s infinite",
        }} />
        <span style={{
          fontFamily: "monospace",
          fontSize:   "11px",
          color:      statusColor,
          letterSpacing: "2px",
        }}>
          {overall.toUpperCase()}
        </span>
      </div>
    </header>
  );
}