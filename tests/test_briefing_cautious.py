from datetime import datetime

from aviation_preflight.briefing import generate_preflight_brief


def test_cautious_partial_decline_for_unknown_aircraft(references_dir, fake_provider) -> None:
    plan = {
        "flight_id": "TEST-CAUTIOUS",
        "departure_airport": "KGAI",
        "destination_airport": "KJYO",
        "departure_time": "2026-06-01T14:30:00-04:00",
        "aircraft_type": "UNKNOWN-PLANE",
        "weights": {
            "pilot_lb": 180,
            "front_passenger_lb": 0,
            "rear_left_lb": 0,
            "rear_right_lb": 0,
            "baggage_lb": 10,
            "fuel_gal": 30,
        },
    }

    brief = generate_preflight_brief(
        plan=plan,
        provider=fake_provider,
        references_dir=references_dir,
        now=datetime.fromisoformat("2026-06-01T12:00:00+00:00"),
    )

    assert brief["status"] == "partial"
    assert brief["weight_balance"]["available"] is False
    assert brief["performance"]["available"] is False
    limitations = " | ".join(brief["limitations"])
    assert "not found" in limitations.lower()
