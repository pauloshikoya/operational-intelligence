# detection/test_narration.py

import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

import anthropic
from detection.prompt_builder import build_prompt


def run_test():

    print("Building prompt...")

    synthetic_context = {
        "anomaly_id":      999,
        "source":          "alpha_vantage",
        "metric_name":     "crude_oil_wti",
        "anomaly_score":   0.78,
        "severity":        "high",
        "dominant_detector": "cusum",
        "current_value":   94.32,
        "historical_avg":  78.45,
        "historical_std":  4.21,
        "z_score":         3.77,
        "pct_change_1d":   2.3,
        "pct_change_7d":   12.4,
        "value_history_text": """
  2024-01-01 00:00   77.820 USD
  2024-01-02 00:00   78.100 USD  +0.4%
  2024-01-03 00:00   77.950 USD  -0.2%
  2024-01-04 00:00   79.200 USD  +1.6%
  2024-01-05 00:00   80.100 USD  +1.1%
  2024-01-06 00:00   82.300 USD  +2.7%
  2024-01-07 00:00   84.100 USD  +2.2%
  2024-01-08 00:00   87.500 USD  +4.0%
  2024-01-09 00:00   90.200 USD  +3.1%
  2024-01-10 00:00   94.320 USD  +4.6%""",
        "related_metrics_text": """
  crude_oil_brent                     value=96.410  z=+3.62  1d=+2.1%  7d=+11.8%
  natural_gas                         value= 3.820  z=+2.10  1d=+3.4%  7d= +8.2%
  copper                              value= 4.120  z=+0.31  1d=+0.2%  7d= +1.1%
  wheat                               value= 5.890  z=+0.45  1d=+0.5%  7d= +2.0%
  weather_disruption_rotterdam_port   value= 0.180  z=+0.22  1d=+0.0%  7d= +5.0%
  weather_disruption_houston_port     value= 0.420  z=+1.80  1d=+8.2%  7d=+22.0%""",
        "past_same_text":    "None in the last 7 days.",
        "past_related_text": """
  natural_gas                         score=0.612  severity=medium  at=2024-01-09 14:23
  weather_disruption_houston_port     score=0.581  severity=medium  at=2024-01-10 06:11""",
        "z_signal":  "Value is 3.8 std devs ABOVE historical average",
        "c_signal":  "Sustained UPWARD drift detected (CUSUM=6.82, threshold=4.0)",
        "if_signal": "Isolation Forest flagged as ANOMALOUS (raw score=-0.621)",
    }

    prompt = build_prompt(synthetic_context)
    print(f"Prompt length: {len(prompt)} characters")
    print("Calling Claude API...")
    print("(waiting for response — this can take 10-20 seconds)...")
    sys.stdout.flush()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in .env file")
        return

    print(f"   Using key: {api_key[:12]}...")
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            temperature=0.2,
            timeout=60.0,
            system=(
                "You are a precision operational intelligence analyst. "
                "You respond ONLY with valid JSON. "
                "Never include markdown, code fences, or any text outside "
                "the JSON object."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        print("Response received!")

    except anthropic.APITimeoutError:
        print("❌ Request timed out after 60 seconds.")
        return
    except anthropic.APIConnectionError as e:
        print(f"❌ Connection error: {e}")
        return
    except anthropic.APIStatusError as e:
        print(f"❌ API error {e.status_code}: {e.message}")
        return

    # ── Extract raw text ───────────────────────────────────────────────────
    raw = response.content[0].text.strip()

    # ── Strip markdown fences if Claude added them ─────────────────────────
    if raw.startswith("```"):
        first_newline = raw.index("\n")
        last_fence    = raw.rfind("```")
        raw           = raw[first_newline + 1 : last_fence].strip()

    # ── Print raw response ─────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("RAW CLAUDE RESPONSE:")
    print("═" * 60)
    print(raw[:3000])

    # ── Parse and display ──────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("PARSED NARRATIVE:")
    print("═" * 60)

    try:
        narrative = json.loads(raw)

        print(f"\nSUMMARY:\n{narrative['summary']}")

        print(f"\nWHAT CHANGED:\n{narrative['what_changed']}")

        print(f"\nLIKELY CAUSES:")
        for i, cause in enumerate(narrative["likely_causes"], 1):
            print(f"  {i}. [{cause['confidence'].upper()}] {cause['cause']}")
            print(f"     → {cause['reasoning']}")

        print(f"\nPATTERN ASSESSMENT:")
        pa = narrative["pattern_assessment"]
        print(f"  Isolated: {pa['is_isolated']}")
        print(f"  {pa['pattern_description']}")
        if pa.get("correlated_metrics"):
            print(f"  Correlated: {', '.join(pa['correlated_metrics'])}")

        print(f"\nRECOMMENDED ACTIONS:")
        for a in narrative["recommended_actions"]:
            print(f"  [{a['urgency'].upper()}] {a['action']}")
            print(f"  → {a['rationale']}")

        print(f"\nDATA SOURCES USED:")
        for d in narrative["data_sources_used"]:
            print(f"  • {d}")

        print(f"\nCAVEATS:")
        for c in narrative["caveats"]:
            print(f"  ⚠ {c}")

        print(f"\nSEVERITY REASONING:\n{narrative['severity_reasoning']}")

        print(
            f"\nTokens: {response.usage.input_tokens} in / "
            f"{response.usage.output_tokens} out"
        )
        cost = (
            response.usage.input_tokens  * (3.0  / 1_000_000) +
            response.usage.output_tokens * (15.0 / 1_000_000)
        )
        print(f"Cost:   ${cost:.4f}")
        print("\n✅ Narration test PASSED")

    except json.JSONDecodeError as e:
        print(f"\n❌ JSON parse failed: {e}")
        print(f"Raw text was:\n{raw}")
    except KeyError as e:
        print(f"\n❌ Missing expected key in response: {e}")
        print(f"Got keys: {list(narrative.keys())}")


if __name__ == "__main__":
    run_test()