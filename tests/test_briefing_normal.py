from datetime import datetime

from aviation_preflight.briefing import generate_preflight_brief, render_brief_markdown


def test_generate_preflight_brief_normal_case(references_dir, fake_provider) -> None:
    plan = {
        "flight_id": "TEST-NORMAL",
        "departure_airport": "KGAI",
        "destination_airport": "KJYO",
        "departure_time": "2026-06-01T14:30:00-04:00",
        "aircraft_type": "PA-28-181",
        "weights": {
            "pilot_lb": 175,
            "front_passenger_lb": 140,
            "rear_left_lb": 0,
            "rear_right_lb": 0,
            "baggage_lb": 30,
            "fuel_gal": 40,
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

    assert brief["status"] == "ok"
    assert brief["route"]["departure"] == "KGAI"
    assert brief["route"]["destination"] == "KJYO"
    assert brief["weight_balance"]["available"] is True
    assert brief["performance"]["available"] is True
    assert brief["advisories"]["tfr"]
    assert isinstance(brief["data_signature"], str)
    assert len(brief["data_signature"]) == 64

    markdown = render_brief_markdown(brief)
    assert "Preflight Briefing" in markdown
    assert "KGAI -> KJYO" in markdown
