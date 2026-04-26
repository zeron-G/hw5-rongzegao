from datetime import datetime

from aviation_preflight.briefing import generate_preflight_brief


def test_unknown_airport_uses_stationinfo_fallback(references_dir, fake_provider) -> None:
    plan = {
        "flight_id": "TEST-STATION-FALLBACK",
        "departure_airport": "KXYZ",
        "destination_airport": "KJYO",
        "departure_time": "2026-06-01T14:30:00-04:00",
        "aircraft_type": "PA-28-181",
        "weights": {
            "pilot_lb": 170,
            "front_passenger_lb": 0,
            "rear_left_lb": 0,
            "rear_right_lb": 0,
            "baggage_lb": 20,
            "fuel_gal": 35,
        },
    }

    brief = generate_preflight_brief(
        plan=plan,
        provider=fake_provider,
        references_dir=references_dir,
        now=datetime.fromisoformat("2026-06-01T12:00:00+00:00"),
    )

    assert brief["route"]["departure"] == "KXYZ"
    assert brief["status"] in {"ok", "partial"}
