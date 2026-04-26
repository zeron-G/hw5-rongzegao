from aviation_preflight.calculations import (
    bilinear_interpolate,
    density_altitude_ft,
    haversine_nm,
    interpolate_envelope_limit,
    interpolate_route_points,
    parse_runway_headings,
    pressure_altitude_ft,
    wind_components_kt,
)


def test_bilinear_interpolate_mid_grid() -> None:
    x_points = [0.0, 10.0]
    y_points = [0.0, 20.0]
    table = [
        [100.0, 200.0],
        [200.0, 300.0],
    ]
    value, x_clamped, y_clamped = bilinear_interpolate(5.0, 10.0, x_points, y_points, table)
    assert value == 200.0
    assert x_clamped is False
    assert y_clamped is False


def test_bilinear_interpolate_clamps_outside_range() -> None:
    x_points = [0.0, 10.0]
    y_points = [0.0, 20.0]
    table = [
        [100.0, 200.0],
        [200.0, 300.0],
    ]
    value, x_clamped, y_clamped = bilinear_interpolate(99.0, -5.0, x_points, y_points, table)
    assert value == 200.0
    assert x_clamped is True
    assert y_clamped is True


def test_interpolate_envelope_limit_linear() -> None:
    points = [
        {"weight_lb": 2000, "forward_in": 84.0, "aft_in": 93.0},
        {"weight_lb": 2500, "forward_in": 87.0, "aft_in": 93.5},
    ]
    forward = interpolate_envelope_limit(2250, points, "forward_in")
    assert round(forward, 2) == 85.5


def test_pressure_and_density_altitude() -> None:
    pa = pressure_altitude_ft(500, 1013.25)
    da = density_altitude_ft(pa, 30)
    assert pa > 450
    assert da > pa


def test_runway_heading_parser() -> None:
    headings = parse_runway_headings("14/32")
    assert headings == [140, 320]


def test_wind_components() -> None:
    headwind, crosswind = wind_components_kt(170, 12, 170)
    assert round(headwind, 1) == 12.0
    assert round(crosswind, 1) == 0.0


def test_route_interpolation_has_endpoints() -> None:
    points = interpolate_route_points(39.0, -77.0, 38.0, -78.0, step_nm=30)
    assert points[0] == (39.0, -77.0)
    assert points[-1] == (38.0, -78.0)
    assert len(points) >= 2


def test_haversine_nonzero() -> None:
    distance = haversine_nm(39.0, -77.0, 39.5, -77.5)
    assert distance > 0.0
