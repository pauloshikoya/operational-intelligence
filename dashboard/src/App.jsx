// src/App.jsx
import { useState }          from "react";
import { Header }            from "./components/Header";
import { StatsBar }          from "./components/StatsBar";
import { AnomalyFeed }       from "./components/AnomalyFeed";
import { AnomalyDetail }     from "./components/AnomalyDetail";
import { MetricGrid }        from "./components/MetricGrid";
import { ScenarioExplorer }  from "./components/ScenarioExplorer";
import { useAnomalies }      from "./hooks/useAnomalies";
import { useStream }         from "./hooks/useStream";

export default function App() {
  const [selectedAnomaly, setSelectedAnomaly] = useState(null);
  const { anomalies, loading, addAnomaly }    = useAnomalies({ hours: 24 });

  // Wire live stream — new anomalies appear at the top of the feed
  useStream((newAnomaly) => {
    addAnomaly(newAnomaly);
  });

  return (
    <div style={{
      height:          "100vh",
      display:         "flex",
      flexDirection:   "column",
      background:      "#080C10",
      color:           "#C8D6E5",
      overflow:        "hidden",
    }}>
      <Header />
      <StatsBar />

      {/* Main content — three columns */}
      <div style={{
        flex:     1,
        display:  "grid",
        gridTemplateColumns: "320px 1fr 280px",
        overflow: "hidden",
        gap:      "1px",
        background: "#1A2332",
      }}>

        {/* Left — anomaly feed */}
        <div style={{
          background:    "#080C10",
          display:       "flex",
          flexDirection: "column",
          overflow:      "hidden",
        }}>
          <div style={{
            padding:       "10px 16px",
            fontFamily:    "monospace",
            fontSize:      "10px",
            color:         "#5A7A94",
            letterSpacing: "2px",
            borderBottom:  "1px solid #1A2332",
            flexShrink:    0,
          }}>
            LIVE ANOMALY FEED
          </div>
          <AnomalyFeed
            anomalies={anomalies}
            loading={loading}
            selectedId={selectedAnomaly?.id}
            onSelect={setSelectedAnomaly}
          />
        </div>

        {/* Centre — anomaly detail */}
        <div style={{
          background:    "#080C10",
          display:       "flex",
          flexDirection: "column",
          overflow:      "hidden",
        }}>
          <AnomalyDetail anomaly={selectedAnomaly} />
        </div>

        {/* Right — metric grid + scenario explorer */}
        <div style={{
          background:    "#080C10",
          display:       "flex",
          flexDirection: "column",
          overflow:      "hidden",
        }}>
          <div style={{ flex: 1, overflowY: "auto", borderBottom: "1px solid #1A2332" }}>
            <MetricGrid />
          </div>
          <div style={{ flexShrink: 0, borderTop: "1px solid #1A2332", overflowY: "auto", maxHeight: "40%" }}>
            <ScenarioExplorer />
          </div>
        </div>

      </div>
    </div>
  );
}