---
name: aviation-preflight-assistant
description: Generate deterministic GA preflight briefings with METAR/TAF pull, nearby AIR/SIGMET/G-AIRMET/TFR checks, PA-28-181 default weight-and-balance/performance math, and automatic T-2h/T-1h briefing scheduling. Use when a user asks for preflight go/no-go style preparation that needs reproducible calculations and live data fetch.
---

# Aviation Preflight Assistant

## When to use
- User wants a preflight briefing for a specific flight (airport + ETD + aircraft loading).
- User needs deterministic weight-and-balance and performance calculations.
- User asks for nearby weather/advisory risk scan: AIR/SIGMET, G-AIRMET, CWA/MIS, and TFR.
- User wants scheduled briefing snapshots at T-120 and T-60 minutes, with update triggers when data changes.

## When not to use
- User needs legal dispatch authority, certified performance dispatch release, or flight service replacement.
- User asks for strategic route optimization, fuel stop optimization, or full flight planning across many legs.
- User requests unsupported jurisdictions/data feeds beyond configured FAA/AWC endpoints.

## Expected inputs
- Flight plan JSON with:
  - `departure_airport` (ICAO)
  - `destination_airport` (ICAO)
  - `departure_time` (ISO datetime with timezone)
  - `aircraft_type` (default expected: `PA-28-181`)
  - `weights` block (`pilot_lb`, passengers, baggage, fuel)
- Optional:
  - `brief_radius_nm`
  - `tfr_radius_nm`
  - `auto_brief_offsets_min`

## Deterministic script (load-bearing)
- Script path: `scripts/preflight_brief.py`
- Core deterministic module: `scripts/aviation_preflight/`
- Why script is required:
  - Bilinear interpolation of takeoff/landing performance tables.
  - Weight-and-balance mass/moment/CG envelope math.
  - Geospatial distance checks between route and advisory polygons.
  - Scheduled T-2h/T-1h auto-trigger logic with data-signature update detection.

## Step-by-step workflow
1. Read flight plan JSON.
2. Resolve airport profile:
   - First local references in `references/airport_profiles.json`
   - Then fallback to live station metadata.
3. Pull live data:
   - METAR, TAF, AIRSIGMET, G-AIRMET, CWA/MIS from AWC.
   - TFR list + geometry from FAA.
4. Compute:
   - W&B totals, CG, envelope checks.
   - Pressure altitude, density altitude, and runway distance estimates.
5. Filter advisories by route proximity thresholds.
6. Produce:
   - Structured JSON payload
   - Markdown pilot-style briefing
7. Optional watch mode:
   - emit at T-120 and T-60
   - emit incremental updates on data signature changes.

## Expected output format
- Markdown preflight briefing:
  - Flight snapshot
  - Weather (METAR/TAF)
  - W&B section
  - Performance section
  - Advisory counts and warnings
  - Limitations
- JSON object with deterministic fields and `data_signature`.

## Important limitations and checks
- This is a training/planning assistant, not an FAA dispatch authority.
- Performance data is profile-based and conservative but simplified.
- If aircraft profile is missing, W&B/performance are partially declined and marked in `limitations`.
- If TAF is missing at airport, fallback stations are attempted and source is disclosed.

## Example commands
```bash
python .agents/skills/aviation-preflight-assistant/scripts/preflight_brief.py brief \
  --plan .agents/skills/aviation-preflight-assistant/references/sample_flight_plan.json \
  --output .briefings/sample_brief.md \
  --json-output .briefings/sample_brief.json
```

```bash
python .agents/skills/aviation-preflight-assistant/scripts/preflight_brief.py watch \
  --plan .agents/skills/aviation-preflight-assistant/references/sample_flight_plan.json \
  --output-dir .briefings \
  --poll-seconds 300
```
