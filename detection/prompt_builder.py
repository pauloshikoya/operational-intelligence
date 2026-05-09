# detection/prompt_builder.py

"""
Prompt Builder
──────────────
Constructs the prompt we send to Claude for anomaly narration.

Prompt engineering principles applied here:

1. ROLE DEFINITION
   Claude needs to know it's acting as an operational intelligence
   analyst, not a general assistant. This affects tone, structure,
   and the level of domain reasoning it applies.

2. STRUCTURED OUTPUT CONTRACT
   We specify EXACTLY what JSON structure we want back.
   Every field is named, typed, and described.
   This makes parsing reliable and the output auditable.

3. DATA BEFORE INSTRUCTION
   We present all the evidence first, then ask Claude to reason
   about it. This mirrors how a good analyst works — look at the
   data, then form conclusions.

4. EXPLICIT UNCERTAINTY
   We instruct Claude to express confidence levels and caveats.
   An intelligence report that never says "uncertain" is dangerous.
   Palantir clients need to know when the AI is confident vs. guessing.

5. GROUNDING REQUIREMENT
   Every claim must reference specific data points.
   This prevents hallucination and makes the output auditable.
"""

from detection.context_builder import build as build_context


# ── Domain knowledge we inject into every prompt ──────────────────────────────
# This is what makes the narratives domain-intelligent rather than generic

DOMAIN_KNOWLEDGE = """
SUPPLY CHAIN DOMAIN KNOWLEDGE (use this to contextualise your analysis):

Commodity interdependencies:
- Crude oil (WTI/Brent) affects: shipping costs, plastics, fertilisers,
  manufacturing inputs. Oil spikes propagate to most other commodities.
- Natural gas affects: fertiliser production (Haber process), European
  industrial output, energy-intensive manufacturing.
- Copper is a leading economic indicator — "Dr Copper" — falling copper
  often precedes economic slowdowns. Rising copper signals industrial demand.
- Wheat spikes often follow: weather disruptions in major growing regions
  (Ukraine, Russia, US Great Plains, Australia), or energy cost increases
  (fertiliser is energy-intensive).
- Aluminum requires enormous electricity — aluminum prices are highly
  sensitive to energy costs and smelter shutdowns.

Port disruption context:
- Rotterdam: Europe's largest port. Disruption here affects European
  manufacturing supply chains significantly.
- Shanghai: World's busiest container port. Any disruption creates
  global ripple effects, especially in electronics and consumer goods.
- Houston: Major US energy hub. Disruptions affect US Gulf Coast
  refining and petrochemical industries.
- Suez Canal: ~12% of global trade transits here. Disruption forces
  ships around Africa, adding ~2 weeks and significant cost.

Anomaly pattern interpretation:
- Multiple commodities spiking simultaneously → likely macro event
  (geopolitical, energy crisis, demand shock)
- Single commodity spike with no related movement → likely
  supply-specific event or data quality issue
- Weather disruption at port coinciding with commodity spike →
  likely physical supply disruption
- Gradual sustained drift (CUSUM signal) → regime change, not noise
- Single-point spike with quick reversion → possible data error or
  thin liquidity event
"""


def build_prompt(context: dict) -> str:
    """
    Build the complete prompt for Claude.

    Args:
        context: the dict returned by context_builder.build()

    Returns:
        A string prompt ready to send to the Claude API.
    """

    prompt = f"""You are an operational intelligence analyst specialising in
global supply chain risk. Your role is to analyse anomalies detected in
commodity price and logistics data, and produce structured intelligence
reports that operations teams can act on.

You must be precise, evidence-based, and appropriately uncertain.
Never fabricate data. Only reference the specific data points provided.
If the data is insufficient to draw a conclusion, say so explicitly.

{DOMAIN_KNOWLEDGE}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANOMALY DETECTED — ANALYSIS REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

METRIC:          {context['metric_name']}
SOURCE:          {context['source']}
ANOMALY SCORE:   {context['anomaly_score']:.3f} / 1.000
SEVERITY:        {context['severity'].upper()}
DOMINANT SIGNAL: {context['dominant_detector']} detector

CURRENT VALUE:   {context['current_value']:.4f}
HISTORICAL AVG:  {context['historical_avg']:.4f}
HISTORICAL STD:  {context['historical_std']:.4f}
Z-SCORE:         {context['z_score']:+.3f}
1-DAY CHANGE:    {context['pct_change_1d']:+.2f}%
7-DAY CHANGE:    {context['pct_change_7d']:+.2f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETECTOR SIGNALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Z-Score detector:          {context['z_signal']}
CUSUM detector:            {context['c_signal']}
Isolation Forest detector: {context['if_signal']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECENT VALUE HISTORY (oldest → newest)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context['value_history_text']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RELATED METRICS (current state)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context['related_metrics_text']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREVIOUS ANOMALIES — SAME METRIC (last 7 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context['past_same_text']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCURRENT ANOMALIES — RELATED METRICS (last 48 hours)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context['past_related_text']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Analyse the above data and produce a structured intelligence report.

You MUST respond with ONLY a valid JSON object. No preamble, no explanation
outside the JSON, no markdown code fences. Raw JSON only.

The JSON must follow this exact structure:

{{
  "summary": "2-3 sentence plain-English summary of what is happening and why it matters operationally. Write for a logistics director who needs to understand this in 20 seconds.",

  "what_changed": "1-2 sentences describing specifically what the data shows changed, referencing concrete values and timeframes from the data above.",

  "likely_causes": [
    {{
      "cause": "Specific cause hypothesis",
      "confidence": "high|medium|low",
      "reasoning": "Brief explanation of why this cause is plausible, referencing specific data points from above."
    }}
  ],

  "pattern_assessment": {{
    "is_isolated": true,
    "pattern_description": "Is this an isolated spike, part of a broader pattern, or a regime change? Reference related metrics and past anomalies in your assessment.",
    "correlated_metrics": ["list of metric names that appear to be moving with this anomaly, if any"]
  }},

  "recommended_actions": [
    {{
      "action": "Specific actionable step",
      "urgency": "immediate|within_24h|within_week|monitor",
      "rationale": "Why this action is warranted by the data"
    }}
  ],

  "data_sources_used": [
    "List each specific data point or statistic from the prompt that informed your analysis"
  ],

  "caveats": [
    "List any important limitations, data quality concerns, or reasons this analysis might be wrong"
  ],

  "severity_reasoning": "Explain in 1-2 sentences why this anomaly warrants the '{context['severity']}' severity rating based on the specific data provided."
}}

Requirements:
- likely_causes: provide 2-4 causes, ordered from most to least likely
- recommended_actions: provide 2-4 actions, ordered by urgency
- data_sources_used: list at least 3 specific data points you referenced
- caveats: list at least 2 caveats (never produce a caveat-free report)
- Every confidence rating must be justified in the reasoning field
- Never invent data not present in the prompt above
"""

    return prompt