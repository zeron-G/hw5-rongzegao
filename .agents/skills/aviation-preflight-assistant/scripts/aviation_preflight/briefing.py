"""Preflight briefing orchestration for the aviation skill."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .calculations import (
    best_runway_for_wind,
    bilinear_interpolate,
    density_altitude_ft,
    flatten_xy_pairs,
    haversine_nm,
    interpolate_envelope_limit,
    interpolate_route_points,
    mercator_to_latlon,
    min_distance_nm_to_points,
    parse_runway_headings,
    pressure_altitude_ft,
)
from .providers import AviationDataProvider, DataProvider

SKILL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCES_DIR = SKILL_ROOT / "references"


def parse_iso_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("Datetime must include timezone info.")
    return parsed


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_reference_data(references_dir: Path | None = None) -> tuple[dict, dict]:
    base = references_dir or DEFAULT_REFERENCES_DIR
    aircraft = _load_json(base / "aircraft_profiles.json")
    airports = _load_json(base / "airport_profiles.json")
    return aircraft, airports


def _normalize_airport(code: str, airport: dict) -> dict:
    profile = deepcopy(airport)
    profile["code"] = code
    runways = profile.get("runways", [])
    for runway in runways:
        if "headings_deg" not in runway or not runway.get("headings_deg"):
            runway["headings_deg"] = parse_runway_headings(str(runway.get("id", "")))
    return profile


def resolve_airport(code: str, airport_profiles: dict, provider: DataProvider) -> dict:
    code_upper = code.upper()
    if code_upper in airport_profiles:
        return _normalize_airport(code_upper, airport_profiles[code_upper])

    stations = provider.get_station_info([code_upper])
    if not stations:
        raise ValueError(f"Airport profile/station info missing for {code_upper}.")

    station = stations[0]
    elevation_raw = float(station.get("elev") or 0)
    # AWC stationinfo elevation is meters.
    elevation_ft = elevation_raw * 3.28084
    resolved = {
        "name": station.get("site", code_upper),
        "lat": float(station["lat"]),
        "lon": float(station["lon"]),
        "elevation_ft": elevation_ft,
        "state": station.get("state", ""),
        "taf_fallback": [],
        "runways": [],
        "notes": [
            "Airport pulled from stationinfo endpoint; "
            "add local profile for runway-aware performance checks."
        ],
    }
    return _normalize_airport(code_upper, resolved)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_weights(weights: dict | None) -> dict:
    source = weights or {}
    result = {
        "pilot_lb": _to_float(source.get("pilot_lb"), 0.0),
        "front_passenger_lb": _to_float(source.get("front_passenger_lb"), 0.0),
        "rear_left_lb": _to_float(source.get("rear_left_lb"), 0.0),
        "rear_right_lb": _to_float(source.get("rear_right_lb"), 0.0),
        "baggage_lb": _to_float(source.get("baggage_lb"), 0.0),
        "fuel_gal": _to_float(source.get("fuel_gal"), 0.0),
    }
    return result


def compute_weight_balance(plan: dict, aircraft_profile: dict | None) -> dict:
    if not aircraft_profile or "weight_balance" not in aircraft_profile:
        return {
            "available": False,
            "warnings": [
                "Weight and balance not computed: aircraft profile missing or incomplete."
            ],
        }

    wb = aircraft_profile["weight_balance"]
    arms = wb["arms_in"]
    weights = _normalize_weights(plan.get("weights"))

    empty_weight_lb = _to_float(wb["empty_weight_lb"])
    empty_moment_lb_in = _to_float(wb["empty_moment_lb_in"])
    fuel_density = _to_float(wb.get("fuel_density_lb_per_gal"), 6.0)

    fuel_lb = weights["fuel_gal"] * fuel_density
    front_total_lb = weights["pilot_lb"] + weights["front_passenger_lb"]
    rear_total_lb = weights["rear_left_lb"] + weights["rear_right_lb"]

    station_weights = [
        ("front_seat", front_total_lb, _to_float(arms["pilot_front"])),
        ("rear_seat", rear_total_lb, _to_float(arms["rear"])),
        ("baggage", weights["baggage_lb"], _to_float(arms["baggage"])),
        ("fuel", fuel_lb, _to_float(arms["fuel"])),
    ]

    total_weight = empty_weight_lb
    total_moment = empty_moment_lb_in
    loading_lines: list[dict] = []

    for station_name, station_weight, station_arm in station_weights:
        station_moment = station_weight * station_arm
        total_weight += station_weight
        total_moment += station_moment
        loading_lines.append(
            {
                "station": station_name,
                "weight_lb": round(station_weight, 2),
                "arm_in": station_arm,
                "moment_lb_in": round(station_moment, 2),
            }
        )

    cg_in = total_moment / total_weight if total_weight else 0.0
    envelope = wb.get("cg_limits", [])
    forward_limit = interpolate_envelope_limit(total_weight, envelope, "forward_in")
    aft_limit = interpolate_envelope_limit(total_weight, envelope, "aft_in")

    warnings: list[str] = []
    max_gross = _to_float(wb.get("max_gross_lb"), 0)
    max_fuel_gal = _to_float(wb.get("max_fuel_gal"), 0)
    if max_gross and total_weight > max_gross:
        warnings.append(f"OVERWEIGHT: {total_weight:.1f} lb exceeds max gross {max_gross:.1f} lb.")
    if max_fuel_gal and weights["fuel_gal"] > max_fuel_gal:
        warnings.append(
            f"Fuel load {weights['fuel_gal']:.1f} gal exceeds listed "
            f"capacity {max_fuel_gal:.1f} gal."
        )
    if cg_in < forward_limit or cg_in > aft_limit:
        warnings.append(
            f"CG OUT OF RANGE: {cg_in:.2f} in (allowed {forward_limit:.2f} - {aft_limit:.2f})."
        )

    in_limits = not warnings
    return {
        "available": True,
        "empty_weight_lb": empty_weight_lb,
        "empty_moment_lb_in": empty_moment_lb_in,
        "total_weight_lb": round(total_weight, 2),
        "total_moment_lb_in": round(total_moment, 2),
        "cg_in": round(cg_in, 2),
        "forward_limit_in": round(forward_limit, 2),
        "aft_limit_in": round(aft_limit, 2),
        "max_gross_lb": max_gross,
        "loading_lines": loading_lines,
        "in_limits": in_limits,
        "warnings": warnings,
    }


def _metar_wind(metar: dict | None) -> tuple[float | None, float]:
    if not metar:
        return None, 0.0
    wdir_raw = metar.get("wdir")
    wind_dir = None if wdir_raw in (None, "VRB") else _to_float(wdir_raw, 0.0)
    wind_speed = _to_float(metar.get("wspd"), 0.0)
    return wind_dir, wind_speed


def _compute_phase_performance(
    aircraft_profile: dict,
    phase: str,
    airport: dict,
    metar: dict | None,
) -> dict:
    phase_key = "takeoff_ground_roll_ft" if phase == "takeoff" else "landing_ground_roll_ft"
    performance = aircraft_profile.get("performance", {})
    table_data = performance.get(phase_key)
    warnings: list[str] = []

    if not table_data:
        return {
            "available": False,
            "warnings": [f"{phase.title()} table missing in aircraft profile."],
        }

    runways = airport.get("runways", [])
    if not runways:
        warnings.append(
            f"{airport['code']}: runway data unavailable. "
            "Distance estimate shown without runway margin."
        )

    temp_c = _to_float(metar.get("temp") if metar else None, 15.0)
    altimeter_hpa = _to_float(metar.get("altim") if metar else None, 1013.25)
    pressure_alt_ft_val = pressure_altitude_ft(
        _to_float(airport.get("elevation_ft"), 0),
        altimeter_hpa,
    )
    density_alt_ft_val = density_altitude_ft(pressure_alt_ft_val, temp_c)

    pressure_axis = [float(v) for v in table_data["pressure_alt_ft"]]
    temp_axis = [float(v) for v in table_data["temp_c"]]
    values = [[float(cell) for cell in row] for row in table_data["values"]]
    base_distance_ft, pa_clamped, temp_clamped = bilinear_interpolate(
        pressure_alt_ft_val, temp_c, pressure_axis, temp_axis, values
    )
    if pa_clamped:
        warnings.append(
            f"{phase.title()} interpolation clamped pressure altitude "
            f"{pressure_alt_ft_val:.0f} ft to table range."
        )
    if temp_clamped:
        warnings.append(
            f"{phase.title()} interpolation clamped temperature {temp_c:.1f} C to table range."
        )

    wind_dir, wind_speed = _metar_wind(metar)
    best_runway = best_runway_for_wind(runways, wind_dir, wind_speed)

    headwind_adjust_ft_per_kt = _to_float(performance.get("headwind_adjust_ft_per_kt"), -10)
    tailwind_adjust_ft_per_kt = _to_float(performance.get("tailwind_adjust_ft_per_kt"), 20)
    crosswind_limit_kt = _to_float(performance.get("crosswind_limit_kt"), 17)

    adjusted_distance = base_distance_ft
    runway_margin = None
    if best_runway:
        headwind = _to_float(best_runway["headwind_kt"], 0.0)
        tailwind = abs(headwind) if headwind < 0 else 0.0
        effective_headwind = headwind if headwind > 0 else 0.0
        adjusted_distance = base_distance_ft + (
            effective_headwind * headwind_adjust_ft_per_kt + tailwind * tailwind_adjust_ft_per_kt
        )
        adjusted_distance = max(adjusted_distance, 0.65 * base_distance_ft)
        length_ft = _to_float(best_runway["length_ft"], 0)
        runway_margin = length_ft / adjusted_distance if adjusted_distance else None

        if best_runway["crosswind_kt"] > crosswind_limit_kt:
            warnings.append(
                f"{phase.title()} crosswind {best_runway['crosswind_kt']:.1f} kt "
                f"exceeds limit {crosswind_limit_kt:.1f} kt."
            )
        if runway_margin is not None and runway_margin < 1.2:
            warnings.append(
                f"{phase.title()} runway margin {runway_margin:.2f} is below "
                "conservative target 1.20."
            )
    else:
        warnings.append(
            f"{phase.title()} runway heading not available; unable to compute wind components."
        )

    return {
        "available": True,
        "phase": phase,
        "airport": airport["code"],
        "oat_c": round(temp_c, 1),
        "altimeter_hpa": round(altimeter_hpa, 1),
        "pressure_alt_ft": round(pressure_alt_ft_val, 0),
        "density_alt_ft": round(density_alt_ft_val, 0),
        "base_distance_ft": round(base_distance_ft, 0),
        "adjusted_distance_ft": round(adjusted_distance, 0),
        "runway_margin_ratio": round(runway_margin, 2) if runway_margin is not None else None,
        "best_runway": best_runway,
        "warnings": warnings,
    }


def compute_performance(
    plan: dict,
    aircraft_profile: dict | None,
    departure_airport: dict,
    destination_airport: dict,
    departure_metar: dict | None,
    destination_metar: dict | None,
) -> dict:
    if not aircraft_profile or "performance" not in aircraft_profile:
        return {
            "available": False,
            "warnings": ["Performance not computed: aircraft profile missing or incomplete."],
        }

    takeoff = _compute_phase_performance(
        aircraft_profile,
        "takeoff",
        departure_airport,
        departure_metar,
    )
    landing = _compute_phase_performance(
        aircraft_profile, "landing", destination_airport, destination_metar
    )
    warnings = [*takeoff.get("warnings", []), *landing.get("warnings", [])]
    return {
        "available": True,
        "takeoff": takeoff,
        "landing": landing,
        "warnings": warnings,
    }


def _normalize_notam_id(value: str) -> str:
    cleaned = value.strip().upper()
    if "-" in cleaned:
        cleaned = cleaned.split("-")[0]
    return cleaned


def _extract_advisory_points(record: dict) -> list[tuple[float, float]]:
    coords = record.get("coords")
    if not isinstance(coords, list):
        return []
    points: list[tuple[float, float]] = []
    for coord in coords:
        if not isinstance(coord, dict):
            continue
        lat = _to_float(coord.get("lat"), None)  # type: ignore[arg-type]
        lon = _to_float(coord.get("lon"), None)  # type: ignore[arg-type]
        if lat is None or lon is None:
            continue
        points.append((lat, lon))
    return points


def _extract_tfr_geometry_points(feature: dict) -> list[tuple[float, float]]:
    geometry = feature.get("geometry", {})
    xy_pairs = flatten_xy_pairs(geometry.get("coordinates", []))
    return [mercator_to_latlon(x, y) for x, y in xy_pairs]


def _nearest_distance_nm(
    route_points: list[tuple[float, float]],
    shape_points: list[tuple[float, float]],
) -> float:
    min_distance = float("inf")
    for shape_lat, shape_lon in shape_points:
        distance = min_distance_nm_to_points(shape_lat, shape_lon, route_points)
        if distance < min_distance:
            min_distance = distance
    return min_distance


def _nearby_airsigmet(
    route_points: list[tuple[float, float]],
    records: list[dict],
    radius_nm: float,
) -> list[dict]:
    nearby: list[dict] = []
    for record in records:
        points = _extract_advisory_points(record)
        if not points:
            continue
        distance = _nearest_distance_nm(route_points, points)
        if distance > radius_nm:
            continue
        nearby.append(
            {
                "source": "AIRSIGMET",
                "air_sigmet_type": record.get("airSigmetType"),
                "hazard": record.get("hazard"),
                "valid_from": record.get("validTimeFrom"),
                "valid_to": record.get("validTimeTo"),
                "distance_nm": round(distance, 1),
                "summary": str(record.get("rawAirSigmet", "")).splitlines()[0][:180],
            }
        )
    return sorted(nearby, key=lambda item: item["distance_nm"])


def _nearby_gairmet(
    route_points: list[tuple[float, float]],
    records: list[dict],
    radius_nm: float,
) -> list[dict]:
    nearby: list[dict] = []
    for record in records:
        points = _extract_advisory_points(record)
        if not points:
            continue
        distance = _nearest_distance_nm(route_points, points)
        if distance > radius_nm:
            continue
        nearby.append(
            {
                "source": "G-AIRMET",
                "hazard": record.get("hazard"),
                "product": record.get("product"),
                "valid_time": record.get("validTime"),
                "distance_nm": round(distance, 1),
                "summary": record.get("due_to", ""),
            }
        )
    return sorted(nearby, key=lambda item: item["distance_nm"])


def _nearby_tfr(
    route_points: list[tuple[float, float]],
    tfr_list: list[dict],
    tfr_geometries: list[dict],
    radius_nm: float,
) -> list[dict]:
    by_notam: dict[str, dict] = {}
    for row in tfr_list:
        notam = _normalize_notam_id(str(row.get("notam_id", "")))
        if not notam:
            continue
        by_notam[notam] = row

    nearby: list[dict] = []
    for feature in tfr_geometries:
        props = feature.get("properties", {})
        notam_key = _normalize_notam_id(str(props.get("NOTAM_KEY", "")))
        points = _extract_tfr_geometry_points(feature)
        if not points:
            continue
        distance = _nearest_distance_nm(route_points, points)
        if distance > radius_nm:
            continue

        list_row = by_notam.get(notam_key, {})
        nearby.append(
            {
                "notam_id": list_row.get("notam_id", notam_key),
                "type": list_row.get("type", props.get("LEGAL", "")),
                "state": list_row.get("state", props.get("STATE", "")),
                "description": list_row.get("description", props.get("TITLE", "")),
                "distance_nm": round(distance, 1),
            }
        )

    return sorted(nearby, key=lambda item: item["distance_nm"])


def _pick_taf(
    airport: dict,
    taf_by_id: dict[str, dict],
    metar_by_id: dict[str, dict],
) -> tuple[str | None, dict | None]:
    code = airport["code"]
    if code in taf_by_id:
        return code, taf_by_id[code]

    for fallback in airport.get("taf_fallback", []):
        fallback_code = fallback.upper()
        if fallback_code in taf_by_id:
            return fallback_code, taf_by_id[fallback_code]

    # Last resort: any airport that has both METAR and TAF can act as nearby proxy.
    for candidate, taf in taf_by_id.items():
        if candidate in metar_by_id and (
            haversine_nm(
                airport["lat"],
                airport["lon"],
                metar_by_id[candidate]["lat"],
                metar_by_id[candidate]["lon"],
            )
            <= 50
        ):
            return candidate, taf

    return None, None


def _metar_warnings(code: str, metar: dict | None) -> list[str]:
    if not metar:
        return [f"{code}: METAR unavailable."]

    warnings: list[str] = []
    flt_cat = str(metar.get("fltCat", "")).upper()
    if flt_cat in {"LIFR", "IFR"}:
        warnings.append(f"{code}: flight category {flt_cat} reported.")
    visib = str(metar.get("visib", ""))
    if visib and visib not in {"10+", "P6SM"} and "1/2" in visib:
        warnings.append(f"{code}: reduced visibility reported ({visib}).")
    return warnings


def _data_signature(raw_payload: dict) -> str:
    packed = json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(packed).hexdigest()


def _risk_level(warnings: list[str]) -> str:
    critical_terms = ["OVERWEIGHT", "CG OUT OF RANGE", "ACTIVE TFR", "runway margin 0."]
    for warning in warnings:
        if any(term in warning for term in critical_terms):
            return "RED"
    return "AMBER" if warnings else "GREEN"


def generate_preflight_brief(
    plan: dict,
    provider: DataProvider | None = None,
    references_dir: Path | None = None,
    now: datetime | None = None,
) -> dict:
    data_provider = provider or AviationDataProvider()
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)

    aircraft_profiles, airport_profiles = load_reference_data(references_dir)

    departure_code = str(plan["departure_airport"]).upper()
    destination_code = str(plan["destination_airport"]).upper()
    departure_time = parse_iso_datetime(str(plan["departure_time"]))
    aircraft_type = str(plan.get("aircraft_type", "")).upper()
    brief_radius_nm = _to_float(plan.get("brief_radius_nm"), 120.0)
    tfr_radius_nm = _to_float(plan.get("tfr_radius_nm"), 80.0)

    limitations: list[str] = []
    warnings: list[str] = []

    departure_airport = resolve_airport(departure_code, airport_profiles, data_provider)
    destination_airport = resolve_airport(destination_code, airport_profiles, data_provider)

    route_points = interpolate_route_points(
        departure_airport["lat"],
        departure_airport["lon"],
        destination_airport["lat"],
        destination_airport["lon"],
    )

    metar_codes = [departure_code, destination_code]
    metars = data_provider.get_metar(metar_codes)
    metar_by_id = {item["icaoId"].upper(): item for item in metars if item.get("icaoId")}

    taf_codes = [departure_code, destination_code]
    taf_codes.extend([code.upper() for code in departure_airport.get("taf_fallback", [])])
    taf_codes.extend([code.upper() for code in destination_airport.get("taf_fallback", [])])
    tafs = data_provider.get_taf(taf_codes)
    taf_by_id = {item["icaoId"].upper(): item for item in tafs if item.get("icaoId")}

    dep_taf_source, dep_taf = _pick_taf(departure_airport, taf_by_id, metar_by_id)
    dest_taf_source, dest_taf = _pick_taf(destination_airport, taf_by_id, metar_by_id)
    if dep_taf is None:
        limitations.append(f"{departure_code}: no TAF available from primary or fallback stations.")
    if dest_taf is None:
        limitations.append(
            f"{destination_code}: no TAF available from primary or fallback stations."
        )

    departure_metar = metar_by_id.get(departure_code)
    destination_metar = metar_by_id.get(destination_code)
    warnings.extend(_metar_warnings(departure_code, departure_metar))
    warnings.extend(_metar_warnings(destination_code, destination_metar))

    airsigmet = data_provider.get_airsigmet()
    gairmet = data_provider.get_gairmet()
    cwa = data_provider.get_cwa()
    mis = data_provider.get_mis()
    tfr_list = data_provider.get_tfr_list()
    tfr_geometries = data_provider.get_tfr_geometries()

    nearby_airsigmet = _nearby_airsigmet(route_points, airsigmet, brief_radius_nm)
    nearby_gairmet = _nearby_gairmet(route_points, gairmet, brief_radius_nm)
    nearby_tfr = _nearby_tfr(route_points, tfr_list, tfr_geometries, tfr_radius_nm)

    if nearby_airsigmet:
        warnings.append(f"AIR/SIGMET within {brief_radius_nm:.0f} NM of route.")
    if nearby_gairmet:
        warnings.append(f"G-AIRMET within {brief_radius_nm:.0f} NM of route.")
    if nearby_tfr:
        warnings.append(f"ACTIVE TFR within {tfr_radius_nm:.0f} NM of route.")

    aircraft_profile = aircraft_profiles.get(aircraft_type)
    if aircraft_profile is None:
        limitations.append(
            f"Aircraft profile '{aircraft_type}' not found. "
            "Weight/performance checks partially declined."
        )

    weight_balance = compute_weight_balance(plan, aircraft_profile)
    warnings.extend(weight_balance.get("warnings", []))

    performance = compute_performance(
        plan,
        aircraft_profile,
        departure_airport,
        destination_airport,
        departure_metar,
        destination_metar,
    )
    warnings.extend(performance.get("warnings", []))

    raw_payload = {
        "metar": metars,
        "taf": tafs,
        "airsigmet": nearby_airsigmet,
        "gairmet": nearby_gairmet,
        "tfr": nearby_tfr,
        "weights": _normalize_weights(plan.get("weights")),
        "aircraft_type": aircraft_type,
        "departure_airport": departure_code,
        "destination_airport": destination_code,
    }
    signature = _data_signature(raw_payload)

    status = "ok" if not limitations else "partial"
    result = {
        "status": status,
        "flight_id": plan.get("flight_id", "UNSPECIFIED"),
        "generated_at": current_time.astimezone(UTC).isoformat(),
        "departure_time": departure_time.isoformat(),
        "route": {"departure": departure_code, "destination": destination_code},
        "aircraft_type": aircraft_type,
        "risk_level": _risk_level(warnings),
        "limitations": limitations,
        "warnings": warnings,
        "weather": {
            "metar": {
                departure_code: departure_metar,
                destination_code: destination_metar,
            },
            "taf": {
                departure_code: {"source": dep_taf_source, "taf": dep_taf},
                destination_code: {"source": dest_taf_source, "taf": dest_taf},
            },
        },
        "advisories": {
            "airsigmet": nearby_airsigmet,
            "gairmet": nearby_gairmet,
            "tfr": nearby_tfr,
            "cwa": cwa,
            "mis": mis,
        },
        "weight_balance": weight_balance,
        "performance": performance,
        "data_signature": signature,
    }
    return result


def render_brief_markdown(brief: dict) -> str:
    flight_id = brief.get("flight_id", "UNSPECIFIED")
    route = brief["route"]
    lines = [
        f"# Preflight Briefing: {flight_id}",
        "",
        f"- Generated (UTC): {brief['generated_at']}",
        f"- Departure Time: {brief['departure_time']}",
        f"- Route: {route['departure']} -> {route['destination']}",
        f"- Aircraft: {brief['aircraft_type']}",
        f"- Risk Level: {brief['risk_level']}",
        f"- Status: {brief['status']}",
        "",
        "## Weather",
    ]

    for airport_code, metar in brief["weather"]["metar"].items():
        if metar:
            lines.append(f"- METAR {airport_code}: `{metar.get('rawOb', 'N/A')}`")
        else:
            lines.append(f"- METAR {airport_code}: unavailable")

    for airport_code, taf_payload in brief["weather"]["taf"].items():
        taf = taf_payload.get("taf")
        source = taf_payload.get("source")
        if taf:
            lines.append(f"- TAF {airport_code} (source {source}): `{taf.get('rawTAF', 'N/A')}`")
        else:
            lines.append(f"- TAF {airport_code}: unavailable")

    lines.append("")
    lines.append("## Weight and Balance")
    wb = brief["weight_balance"]
    if wb.get("available"):
        lines.extend(
            [
                f"- Total Weight: {wb['total_weight_lb']} lb (max {wb['max_gross_lb']} lb)",
                f"- CG: {wb['cg_in']} in (limits {wb['forward_limit_in']} - {wb['aft_limit_in']})",
                f"- Within Limits: {wb['in_limits']}",
            ]
        )
    else:
        lines.append("- Not available.")

    lines.append("")
    lines.append("## Performance")
    perf = brief["performance"]
    if perf.get("available"):
        tkof = perf["takeoff"]
        ldg = perf["landing"]
        lines.append(
            f"- Takeoff adjusted roll ({tkof['airport']}): {tkof['adjusted_distance_ft']} ft, "
            f"margin={tkof['runway_margin_ratio']}"
        )
        lines.append(
            f"- Landing adjusted roll ({ldg['airport']}): {ldg['adjusted_distance_ft']} ft, "
            f"margin={ldg['runway_margin_ratio']}"
        )
    else:
        lines.append("- Not available.")

    lines.append("")
    lines.append("## Nearby Advisories")
    lines.append(f"- AIR/SIGMET: {len(brief['advisories']['airsigmet'])}")
    lines.append(f"- G-AIRMET: {len(brief['advisories']['gairmet'])}")
    lines.append(f"- TFR: {len(brief['advisories']['tfr'])}")
    lines.append(f"- CWA: {len(brief['advisories']['cwa'])}")

    if brief.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for warning in brief["warnings"]:
            lines.append(f"- {warning}")

    if brief.get("limitations"):
        lines.append("")
        lines.append("## Limitations")
        for limitation in brief["limitations"]:
            lines.append(f"- {limitation}")

    return "\n".join(lines).rstrip() + "\n"
