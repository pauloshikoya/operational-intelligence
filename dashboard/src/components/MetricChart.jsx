// src/components/MetricChart.jsx
import { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { format } from "date-fns";
import { api } from "../lib/api";

export function MetricChart({ metricName, anomalyTime }) {
  const [series,   setSeries]   = useState([]);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    if (!metricName) return;
    setLoading(true);
    api.getMetricSeries(metricName, 168)
      .then((data) => {
        setSeries(
          (data.series || []).map((p) => ({
            time:  new Date(p.ingested_at).getTime(),
            value: parseFloat(p.value),
          }))
        );
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [metricName]);

  if (loading) {
    return (
      <div style={{ padding: "24px", color: "#3A5A74",
                    fontFamily: "monospace", fontSize: "11px" }}>
        LOADING CHART...
      </div>
    );
  }

  if (!series.length) {
    return (
      <div style={{ padding: "24px", color: "#3A5A74",
                    fontFamily: "monospace", fontSize: "11px" }}>
        NO DATA AVAILABLE
      </div>
    );
  }

  const anomalyTs = anomalyTime ? new Date(anomalyTime).getTime() : null;

  return (
    <div style={{ width: "100%", height: 180 }}>
      <ResponsiveContainer>
        <LineChart data={series} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <XAxis
            dataKey="time"
            tickFormatter={(t) => format(new Date(t), "MM/dd")}
            tick={{ fill: "#3A5A74", fontSize: 10, fontFamily: "monospace" }}
            axisLine={{ stroke: "#1A2332" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#3A5A74", fontSize: 10, fontFamily: "monospace" }}
            axisLine={{ stroke: "#1A2332" }}
            tickLine={false}
            width={55}
          />
          <Tooltip
            contentStyle={{
              background:   "#0D1520",
              border:       "1px solid #1A2332",
              borderRadius: "4px",
              fontFamily:   "monospace",
              fontSize:     "11px",
              color:        "#F0F4F8",
            }}
            labelFormatter={(t) => format(new Date(t), "MMM dd HH:mm")}
            formatter={(v) => [v.toFixed(4), "value"]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#00FFB2"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 4, fill: "#00FFB2" }}
          />
          {anomalyTs && (
            <ReferenceLine
              x={anomalyTs}
              stroke="#FF6B35"
              strokeDasharray="4 4"
              label={{
                value:    "⚠",
                position: "top",
                fill:     "#FF6B35",
                fontSize: 14,
              }}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}