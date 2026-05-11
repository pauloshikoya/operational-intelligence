// src/components/ScenarioExplorer.jsx
import { useState } from "react";
import { api }      from "../lib/api";
import { Send }     from "lucide-react";

const SUGGESTIONS = [
  "Which metrics are most anomalous right now?",
  "Is the oil price movement isolated or correlated?",
  "What happened with energy prices in the last 24 hours?",
  "Are any port disruptions affecting commodities?",
];

export function ScenarioExplorer() {
  const [question, setQuestion] = useState("");
  const [answer,   setAnswer]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);

  async function submit(q) {
    const text = q || question;
    if (!text.trim() || text.length < 5) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const data = await api.ask(text);
      setAnswer(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{
        fontFamily:    "monospace",
        fontSize:      "10px",
        color:         "#5A7A94",
        letterSpacing: "2px",
      }}>
        SCENARIO EXPLORER
      </div>

      {/* Suggestions */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => { setQuestion(s); submit(s); }}
            style={{
              background:   "#0D1520",
              border:       "1px solid #1A2332",
              borderRadius: "4px",
              padding:      "4px 10px",
              fontFamily:   "monospace",
              fontSize:     "10px",
              color:        "#7A9AB5",
              cursor:       "pointer",
            }}
          >
            {s.length > 40 ? s.slice(0, 40) + "…" : s}
          </button>
        ))}
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: "8px" }}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Ask about your data..."
          style={{
            flex:         1,
            background:   "#0D1520",
            border:       "1px solid #1A2332",
            borderRadius: "4px",
            padding:      "8px 12px",
            fontFamily:   "monospace",
            fontSize:     "12px",
            color:        "#F0F4F8",
            outline:      "none",
          }}
        />
        <button
          onClick={() => submit()}
          disabled={loading}
          style={{
            background:   "#00FFB2",
            border:       "none",
            borderRadius: "4px",
            padding:      "8px 12px",
            cursor:       loading ? "not-allowed" : "pointer",
            opacity:      loading ? 0.5 : 1,
            display:      "flex",
            alignItems:   "center",
          }}
        >
          <Send size={14} color="#080C10" />
        </button>
      </div>

      {/* Answer */}
      {loading && (
        <div style={{ fontFamily: "monospace", fontSize: "11px", color: "#3A5A74" }}>
          QUERYING INTELLIGENCE...
        </div>
      )}
      {error && (
        <div style={{ fontFamily: "monospace", fontSize: "11px", color: "#FF4444" }}>
          ERROR: {error}
        </div>
      )}
      {answer && (
        <div style={{
          background:   "#0D1520",
          border:       "1px solid #1A2F45",
          borderRadius: "6px",
          padding:      "12px 16px",
        }}>
          <div style={{
            fontFamily:    "monospace",
            fontSize:      "10px",
            color:         "#00FFB2",
            letterSpacing: "2px",
            marginBottom:  "8px",
          }}>
            INTELLIGENCE RESPONSE
          </div>
          <div style={{
            fontFamily: "monospace",
            fontSize:   "12px",
            color:      "#8AB0CC",
            lineHeight: "1.7",
          }}>
            {answer.answer}
          </div>
          <div style={{
            marginTop:  "8px",
            fontFamily: "monospace",
            fontSize:   "10px",
            color:      "#3A5A74",
          }}>
            {answer.tokens_used} tokens used
          </div>
        </div>
      )}
    </div>
  );
}