from datetime import datetime

from aviation_preflight.scheduler import WatchEvent, run_watch_loop


def test_watch_loop_emits_scheduled_and_update_events() -> None:
    departure_time = datetime.fromisoformat("2026-06-01T14:00:00+00:00")
    now_sequence = iter(
        [
            datetime.fromisoformat("2026-06-01T11:50:00+00:00"),
            datetime.fromisoformat("2026-06-01T12:00:00+00:00"),
            datetime.fromisoformat("2026-06-01T13:00:00+00:00"),
            datetime.fromisoformat("2026-06-01T13:10:00+00:00"),
            datetime.fromisoformat("2026-06-01T14:20:00+00:00"),
        ]
    )
    signatures = iter(["A", "A", "A", "B", "B"])

    def generate_fn(_: datetime) -> dict:
        return {"data_signature": next(signatures), "flight_id": "TEST"}

    captured: list[WatchEvent] = []

    def emit_fn(event: WatchEvent) -> None:
        captured.append(event)

    def now_fn() -> datetime:
        return next(now_sequence)

    run_watch_loop(
        departure_time=departure_time,
        offsets_min=[120, 60],
        generate_fn=generate_fn,
        emit_fn=emit_fn,
        now_fn=now_fn,
        sleep_fn=lambda _: None,
        poll_seconds=0,
        max_iterations=5,
    )

    assert len(captured) == 3
    assert captured[0].event_type == "scheduled"
    assert captured[0].label == "T-120m"
    assert captured[1].event_type == "scheduled"
    assert captured[1].label == "T-60m"
    assert captured[2].event_type == "update"
    assert captured[2].label == "DATA-UPDATE"
