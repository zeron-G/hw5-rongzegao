# Week 5 - Reusable AI Skill: Aviation Preflight Assistant

## Video demo
- Walkthrough video (45-90s): https://youtu.be/vmC_eKf8tN8

## What this skill does
`aviation-preflight-assistant` is a narrow, reusable skill for GA preflight preparation.

It combines:
- live METAR/TAF pull
- nearby AIRSIGMET / G-AIRMET / CWA(MIS) / TFR checks
- deterministic PA-28-181 weight-and-balance + performance calculations
- automatic T-120 / T-60 briefing scheduling with update-on-data-change behavior

Default profile:
- Departure airport: `KGAI`
- Aircraft: `PA-28-181`

The design still supports other airports and aircraft profiles.

## Why I chose this idea
Preflight briefing is a realistic workflow where prose alone is not enough. The script is load-bearing because it must do deterministic tasks:
- moment/CG computation and envelope checks
- interpolation-based performance estimates
- geospatial proximity checks for advisories/TFR polygons
- reproducible scheduler logic for T-2h and T-1h brief generation

## Repository structure
```text
hw5-rongzegao/
├─ .agents/
│  └─ skills/
│     └─ aviation-preflight-assistant/
│        ├─ SKILL.md
│        ├─ references/
│        │  ├─ aircraft_profiles.json
│        │  ├─ airport_profiles.json
│        │  └─ sample_flight_plan.json
│        └─ scripts/
│           ├─ preflight_brief.py
│           └─ aviation_preflight/
│              ├─ briefing.py
│              ├─ calculations.py
│              ├─ providers.py
│              └─ scheduler.py
├─ tests/
├─ .github/workflows/ci.yml
├─ pyproject.toml
└─ README.md
```

## How to use
### 1) Install
```bash
pip install -e .
pip install pytest pytest-cov ruff
```

### 2) Single preflight brief
```bash
python .agents/skills/aviation-preflight-assistant/scripts/preflight_brief.py brief \
  --plan .agents/skills/aviation-preflight-assistant/references/sample_flight_plan.json \
  --output .briefings/sample_brief.md \
  --json-output .briefings/sample_brief.json
```

### 3) Watch mode (auto T-2h / T-1h)
```bash
python .agents/skills/aviation-preflight-assistant/scripts/preflight_brief.py watch \
  --plan .agents/skills/aviation-preflight-assistant/references/sample_flight_plan.json \
  --output-dir .briefings \
  --poll-seconds 300
```

## Script responsibilities
`scripts/preflight_brief.py` orchestrates:
- load plan
- call live providers (AWC + FAA)
- run deterministic calculation modules
- output Markdown + JSON
- run watch scheduler for pre-departure auto briefs

## Prompt tests (required 3 cases)
I validated with 3 representative prompts:

1. Normal case
- "Generate a preflight brief for KGAI -> KJYO today at 14:30 local with PA-28-181."

2. Edge case
- "Same route but four passengers, full fuel, heavy baggage; highlight limits."

3. Cautious/partial decline case
- "Use unknown aircraft profile `UNKNOWN-PLANE`; still provide what you can and flag limits."

## Test and CI
### Local test
```bash
ruff check .
pytest
```

### CI
GitHub Actions workflow: `.github/workflows/ci.yml`
- Python 3.11 and 3.12
- `ruff check .`
- `pytest` with coverage threshold (`--cov-fail-under=85`)

## What worked well
- The skill remains narrow and reusable.
- The script does essential deterministic work, not decorative code.
- Fallback logic handles missing TAF at small airports.
- Watch loop supports scheduled + data-change-triggered updates.

## Remaining limitations
- Performance tables are profile-based and simplified.
- CWA feed can be sparse; MIS is used as an operational fallback.
- This is a training/planning assistant, not a certified dispatch release.
