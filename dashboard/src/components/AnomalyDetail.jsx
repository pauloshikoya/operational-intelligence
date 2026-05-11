// src/components/AnomalyDetail.jsx
import { useState, useEffect } from "react";
import { api }         from "../lib/api";
import { MetricChart } from "./MetricChart";

function CauseCard({ cause, index }) {
  const confidenceColor = {
    high:   "#00FFB2",
    medium: "#FFB800",
    low:    "#FF6B35",
  }[cause.confidence] || "#5A7A94";

  return (
    <div style={{
      background:   "#080C10",
      border:       "1px solid #1A2332",
      borderRadius: "6px",
      padding:      "12px 16px",
      marginBottom: "8px",
    }}>
      <div style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
        <span style={{
          fontFamily:    "monospace",
          fontSize:      "10px",
          color:         confidenceColor,
          border:        `1px solid ${confidenceColor}44`,
          borderRadius:  "3px",
          padding:       "2px 6px",
          flexShrink:    0,
          marginTop:     "2px",
        }}>
          {cause.confidence?.toUpperCase()}
        </span>
        <div>
          <div style={{
            fontFamily:   "monospace",
            fontSize:     "12px",
            color:        "#D0E4F4",
            fontWeight:   "600",
            marginBottom: "4px",
          }}>
            {cause.cause}
          </div>
          <div style={{
            fontFamily: "monospace",
            fontSize:   "11px",
            color:      "#5A7A94",
            lineHeight: "1.6",
          }}>
            {cause.reasoning}
          </div>
        </div>
      </div>
    </div>
  );
}

function ActionCard({ action }) {
  const urgencyColor = {
    immediate:    "#FF4444",
    within_24h:   "#FF6B35",
    within_week:  "#FFB800",
    monitor:      "#7B61FF",
  }[action.urgency] || "#5A7A94";

  return (
    <div style={{
      display:      "flex",
      gap:          "12px",
      padding:      "10px 0",
      borderBottom: "1px solid #1A2332",
    }}>
      <span style={{
        fontFamily:    "monospace",
        fontSize:      "9px",
        color:         urgencyColor,
        border:        `1px solid ${urgencyColor}44`,
        borderRadius:  "3px",
        padding:       "3px 6px",
        flexShrink:    0,
        height:        "fit-content",
        marginTop:     "2px",
        letterSpacing: "1px",
      }}>
        {action.urgency?.replace(/_/g, " ").toUpperCase()}
      </span>
      <div>
        <div style={{
          fontFamily: "monospace",
          fontSize:   "12px",
          color:      "#D0E4F4",
          marginBottom: "3px",
        }}>
          {action.action}
        </div>
        <div style={{
          fontFamily: "monospace",
          fontSize:   "11px",
          color:      "#5A7A94",
          lineHeight: "1.5",
        }}>
          {action.rationale}
        </div>
      </div>
    </div>
  );
}

export function AnomalyDetail({ anomaly }) {
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab,     setTab]     = useState("narrative");

  useEffect(() => {
    if (!anomaly) return;
    setLoading(true);
    setDetail(null);
    api.getAnomaly(anomaly.id)
      .then(setDetail)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [anomaly?.id]);

  if (!anomaly) {
    return (
      <div style={{
        flex:           1,
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        color:          "#3A5A74",
        fontFamily:     "monospace",
        fontSize:       "12px",
        letterSpacing:  "2px",
      }}>
        ← SELECT AN ANOMALY TO INVESTIGATE
      </div>
    );
  }

  const narrative = detail?.narrative_json;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px" }}>

      {/* Header */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{
          fontFamily:    "monospace",
          fontSize:      "10px",
          color:         "#5A7A94",
          letterSpacing: "2px",
          marginBottom:  "6px",
        }}>
          ANOMALY #{anomaly.id} · {anomaly.source}
        </div>
        <div style={{
          fontFamily:   "monospace",
          fontSize:     "18px",
          fontWeight:   "700",
          color:        "#F0F4F8",
          marginBottom: "8px",
        }}>
          {anomaly.metric_name?.replace(/_/g, " ").toUpperCase()}
        </div>
        <div style={{ display: "flex", gap: "12px" }}>
          {[
            ["SCORE",    Number(anomaly.anomaly_score).toFixed(3)],
            ["SEVERITY", anomaly.severity?.toUpperCase()],
          ].map(([k, v]) => (
            <div key={k} style={{
              background:   "#1A2332",
              borderRadius: "4px",
              padding:      "4px 10px",
              fontFamily:   "monospace",
              fontSize:     "11px",
              color:        "#7A9AB5",
            }}>
              {k}: <span style={{ color: "#F0F4F8" }}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div style={{
        background:   "#0D1520",
        border:       "1px solid #1A2332",
        borderRadius: "6px",
        padding:      "12px",
        marginBottom: "16px",
      }}>
        <div style={{
          fontFamily:    "monospace",
          fontSize:      "10px",
          color:         "#5A7A94",
          letterSpacing: "2px",
          marginBottom:  "8px",
        }}>
          7-DAY PRICE HISTORY
        </div>
        <MetricChart
          metricName={anomaly.metric_name}
          anomalyTime={anomaly.triggered_at}
        />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "4px", marginBottom: "16px" }}>
        {["narrative", "causes", "actions", "caveats"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background:    tab === t ? "#1A2F4A" : "transparent",
              border:        tab === t ? "1px solid #2A4A6A" : "1px solid transparent",
              color:         tab === t ? "#00FFB2" : "#5A7A94",
              padding:       "6px 14px",
              borderRadius:  "4px",
              cursor:        "pointer",
              fontFamily:    "monospace",
              fontSize:      "10px",
              letterSpacing: "1px",
            }}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loading && (
        <div style={{ color: "#3A5A74", fontFamily: "monospace", fontSize: "11px" }}>
          LOADING INTELLIGENCE REPORT...
        </div>
      )}

      {!loading && !narrative && (
        <div style={{ color: "#3A5A74", fontFamily: "monospace", fontSize: "11px" }}>
          NARRATIVE NOT YET GENERATED
        </div>
      )}

      {!loading && narrative && (
        <>
          {tab === "narrative" && (
            <div style={{
              fontFamily: "monospace",
              fontSize:   "13px",
              color:      "#8AB0CC",
              lineHeight: "1.8",
              background: "#0D1520",
              border:     "1px solid #1A2332",
              borderRadius: "6px",
              padding:    "16px",
            }}>
              <div style={{ color: "#00FFB2", fontSize: "10px", letterSpacing: "2px", marginBottom: "8px" }}>
                SUMMARY
              </div>
              {narrative.summary}
              {narrative.what_changed && (
                <>
                  <div style={{ color: "#00FFB2", fontSize: "10px", letterSpacing: "2px", margin: "16px 0 8px" }}>
                    WHAT CHANGED
                  </div>
                  {narrative.what_changed}
                </>
              )}
              {narrative.severity_reasoning && (
                <>
                  <div style={{ color: "#00FFB2", fontSize: "10px", letterSpacing: "2px", margin: "16px 0 8px" }}>
                    SEVERITY REASONING
                  </div>
                  {narrative.severity_reasoning}
                </>
              )}
            </div>
          )}

          {tab === "causes" && (
            <div>
              {(narrative.likely_causes || []).map((c, i) => (
                <CauseCard key={i} cause={c} index={i} />
              ))}
            </div>
          )}

          {tab === "actions" && (
            <div>
              {(narrative.recommended_actions || []).map((a, i) => (
                <ActionCard key={i} action={a} />
              ))}
            </div>
          )}

          {tab === "caveats" && (
            <div style={{
              fontFamily: "monospace",
              fontSize:   "12px",
            }}>
              {(narrative.caveats || []).map((c, i) => (
                <div key={i} style={{
                  display:      "flex",
                  gap:          "10px",
                  padding:      "10px 0",
                  borderBottom: "1px solid #1A2332",
                  color:        "#8AB0CC",
                  lineHeight:   "1.6",
                }}>
                  <span style={{ color: "#FFB800", flexShrink: 0 }}>⚠</span>
                  {c}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}