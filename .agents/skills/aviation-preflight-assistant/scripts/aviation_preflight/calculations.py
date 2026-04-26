"""Deterministic math utilities for the aviation preflight skill."""

from __future__ import annotations

import math
from collections.abc import Iterable

EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat / 2) ** 2 + (
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_NM * c


def interpolate_route_points(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    step_nm: float = 20.0,
) -> list[tuple[float, float]]:
    """Interpolate simple route points between departure and destination."""
    distance_nm = haversine_nm(start_lat, start_lon, end_lat, end_lon)
    if distance_nm == 0:
        return [(start_lat, start_lon)]

    segments = max(1, int(math.ceil(distance_nm / step_nm)))
    points: list[tuple[float, float]] = []
    for index in range(segments + 1):
        t = index / segments
        lat = start_lat + (end_lat - start_lat) * t
        lon = start_lon + (end_lon - start_lon) * t
        points.append((lat, lon))
    return points


def _bound_index(points: list[float], value: float) -> tuple[int, int]:
    if value <= points[0]:
        return 0, 0
    if value >= points[-1]:
        last = len(points) - 1
        return last, last

    for index in range(len(points) - 1):
        left = points[index]
        right = points[index + 1]
        if left <= value <= right:
            return index, index + 1

    last = len(points) - 1
    return last, last


def _lerp(x: float, x1: float, x2: float, q1: float, q2: float) -> float:
    if x1 == x2:
        return q1
    ratio = (x - x1) / (x2 - x1)
    return q1 + ratio * (q2 - q1)


def bilinear_interpolate(
    x: float,
    y: float,
    x_points: list[float],
    y_points: list[float],
    table: list[list[float]],
) -> tuple[float, bool, bool]:
    """
    Bilinear interpolation over a rectangular grid.

    Returns:
      (value, x_clamped, y_clamped)
    """
    if not x_points or not y_points:
        raise ValueError("x_points and y_points must not be empty.")
    if len(table) != len(x_points):
        raise ValueError("Table row count must match x_points length.")
    if any(len(row) != len(y_points) for row in table):
        raise ValueError("Each table row must match y_points length.")

    x_clamped = x < x_points[0] or x > x_points[-1]
    y_clamped = y < y_points[0] or y > y_points[-1]

    x_use = min(max(x, x_points[0]), x_points[-1])
    y_use = min(max(y, y_points[0]), y_points[-1])

    x1_idx, x2_idx = _bound_index(x_points, x_use)
    y1_idx, y2_idx = _bound_index(y_points, y_use)

    q11 = table[x1_idx][y1_idx]
    q12 = table[x1_idx][y2_idx]
    q21 = table[x2_idx][y1_idx]
    q22 = table[x2_idx][y2_idx]

    x1 = x_points[x1_idx]
    x2 = x_points[x2_idx]
    y1 = y_points[y1_idx]
    y2 = y_points[y2_idx]

    if x1 == x2 and y1 == y2:
        return q11, x_clamped, y_clamped
    if x1 == x2:
        value = _lerp(y_use, y1, y2, q11, q12)
        return value, x_clamped, y_clamped
    if y1 == y2:
        value = _lerp(x_use, x1, x2, q11, q21)
        return value, x_clamped, y_clamped

    r1 = _lerp(x_use, x1, x2, q11, q21)
    r2 = _lerp(x_use, x1, x2, q12, q22)
    value = _lerp(y_use, y1, y2, r1, r2)
    return value, x_clamped, y_clamped


def interpolate_envelope_limit(weight_lb: float, points: list[dict], key: str) -> float:
    """Interpolate a weight-and-balance envelope limit linearly."""
    if not points:
        raise ValueError("Envelope points cannot be empty.")
    points_sorted = sorted(points, key=lambda item: float(item["weight_lb"]))

    low = points_sorted[0]
    high = points_sorted[-1]
    if weight_lb <= float(low["weight_lb"]):
        return float(low[key])
    if weight_lb >= float(high["weight_lb"]):
        return float(high[key])

    for index in range(len(points_sorted) - 1):
        left = points_sorted[index]
        right = points_sorted[index + 1]
        left_w = float(left["weight_lb"])
        right_w = float(right["weight_lb"])
        if left_w <= weight_lb <= right_w:
            return _lerp(weight_lb, left_w, right_w, float(left[key]), float(right[key]))

    return float(high[key])


def pressure_altitude_ft(field_elevation_ft: float, altimeter_hpa: float) -> float:
    """Compute pressure altitude from field elevation and altimeter setting in hPa."""
    inhg = altimeter_hpa / 33.8638866667
    return field_elevation_ft + (29.92 - inhg) * 1000.0


def density_altitude_ft(pressure_alt_ft: float, oat_c: float) -> float:
    """Approximate density altitude from pressure altitude and OAT."""
    isa_temp = 15 - 2 * (pressure_alt_ft / 1000.0)
    return pressure_alt_ft + 120 * (oat_c - isa_temp)


def parse_runway_headings(runway_id: str) -> list[int]:
    """Parse runway headings in degrees from IDs like '14/32'."""
    headings: list[int] = []
    for part in runway_id.split("/"):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            continue
        heading = int(digits[:2]) * 10
        if heading == 0:
            heading = 360
        headings.append(heading)
    return headings


def wind_components_kt(
    wind_dir_deg: float | None,
    wind_speed_kt: float,
    runway_heading_deg: float,
) -> tuple[float, float]:
    """
    Return (headwind, crosswind) components in knots.

    Crosswind is absolute magnitude.
    """
    if wind_dir_deg is None:
        return 0.0, 0.0
    angle_rad = math.radians(wind_dir_deg - runway_heading_deg)
    headwind = wind_speed_kt * math.cos(angle_rad)
    crosswind = abs(wind_speed_kt * math.sin(angle_rad))
    return headwind, crosswind


def best_runway_for_wind(
    runways: Iterable[dict],
    wind_dir_deg: float | None,
    wind_speed_kt: float,
) -> dict | None:
    """Choose runway end with strongest headwind / weakest crosswind profile."""
    best: dict | None = None
    best_score = float("-inf")
    for runway in runways:
        headings = runway.get("headings_deg")
        if not headings:
            headings = parse_runway_headings(str(runway.get("id", "")))
        if not headings:
            continue

        for heading in headings:
            headwind, crosswind = wind_components_kt(wind_dir_deg, wind_speed_kt, heading)
            score = headwind - 0.5 * crosswind
            if score > best_score:
                best_score = score
                best = {
                    "runway_id": runway.get("id"),
                    "heading_deg": heading,
                    "length_ft": float(runway.get("length_ft", 0)),
                    "surface": runway.get("surface", "UNKNOWN"),
                    "headwind_kt": headwind,
                    "crosswind_kt": crosswind,
                }
    return best


def mercator_to_latlon(x_m: float, y_m: float) -> tuple[float, float]:
    """Convert EPSG:3857 meters to lat/lon degrees."""
    lon = (x_m / 20037508.34) * 180.0
    lat = (y_m / 20037508.34) * 180.0
    lat = math.degrees(2 * math.atan(math.exp(math.radians(lat))) - math.pi / 2)
    return lat, lon


def flatten_xy_pairs(nested: object) -> list[tuple[float, float]]:
    """Flatten nested coordinate arrays into (x, y) pairs."""
    pairs: list[tuple[float, float]] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            if (
                len(node) == 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
            ):
                pairs.append((float(node[0]), float(node[1])))
                return
            for child in node:
                walk(child)

    walk(nested)
    return pairs


def min_distance_nm_to_points(
    point_lat: float,
    point_lon: float,
    candidates: Iterable[tuple[float, float]],
) -> float:
    """Compute minimum distance from one point to a list of points."""
    min_distance = float("inf")
    for lat, lon in candidates:
        distance = haversine_nm(point_lat, point_lon, lat, lon)
        if distance < min_distance:
            min_distance = distance
    return min_distance
