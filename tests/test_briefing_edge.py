from datetime import datetime

from aviation_preflight.briefing import generate_preflight_brief


def test_edge_case_taf_fallback_and_overweight(references_dir, fake_provider) -> None:
    plan = {
        "flight_id": "TEST-EDGE",
        "departure_airport": "KGAI",
        "destination_airport": "KJYO",
        "departure_time": "2026-06-01T14:30:00-04:00",
        "aircraft_type": "PA-28-181",
        "weights": {
            "pilot_lb": 220,
            "front_passenger_lb": 220,
            "rear_left_lb": 210,
            "rear_right_lb": 190,
            "baggage_lb": 100,
            "fuel_gal": 50,
        },
        "brief_radius_nm": 120,
        "tfr_radius_nm": 80,
    }

    brief = generate_preflight_brief(
        plan=plan,
        provider=fake_provider,
        references_dir=references_dir,
        now=datetime.fromisoformat("2026-06-01T12:00:00+00:00"),
    )

    departure_taf = brief["weather"]["taf"]["KGAI"]
    assert departure_taf["source"] == "KIAD"
    assert departure_taf["taf"] is not None

    warnings_text = " | ".join(brief["warnings"])
    assert "OVERWEIGHT" in warnings_text
    assert brief["weight_balance"]["in_limits"] is False
