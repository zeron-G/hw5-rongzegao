"""Scheduler logic for T-2h / T-1h brief generation and update triggers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class WatchEvent:
    event_type: str
    label: str
    emitted_at: datetime
    data_signature: str
    briefing: dict


def run_watch_loop(
    departure_time: datetime,
    offsets_min: list[int],
    generate_fn: Callable[[datetime], dict],
    emit_fn: Callable[[WatchEvent], None],
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    poll_seconds: int = 300,
    max_iterations: int = 0,
) -> list[WatchEvent]:
    """
    Run watch loop and emit events for scheduled and data-update briefings.

    Stops when:
    - max_iterations reached (if > 0), or
    - all scheduled offsets emitted and now > departure + 15 minutes.
    """
    offsets = sorted({int(item) for item in offsets_min if int(item) > 0}, reverse=True)
    emitted_offsets: set[int] = set()
    events: list[WatchEvent] = []
    previous_signature: str | None = None
    iteration = 0

    while True:
        now = now_fn()
        briefing = generate_fn(now)
        signature = str(briefing.get("data_signature", ""))

        scheduled_emitted = False
        for offset in offsets:
            if offset in emitted_offsets:
                continue
            trigger_time = departure_time - timedelta(minutes=offset)
            if now >= trigger_time:
                event = WatchEvent(
                    event_type="scheduled",
                    label=f"T-{offset}m",
                    emitted_at=now,
                    data_signature=signature,
                    briefing=briefing,
                )
                emit_fn(event)
                events.append(event)
                emitted_offsets.add(offset)
                scheduled_emitted = True

        if (
            not scheduled_emitted
            and emitted_offsets
            and previous_signature
            and signature != previous_signature
        ):
            # Live data changed after schedule started, emit update brief.
            event = WatchEvent(
                event_type="update",
                label="DATA-UPDATE",
                emitted_at=now,
                data_signature=signature,
                briefing=briefing,
            )
            emit_fn(event)
            events.append(event)

        previous_signature = signature
        iteration += 1

        if max_iterations > 0 and iteration >= max_iterations:
            break

        if len(emitted_offsets) == len(offsets) and now > departure_time + timedelta(minutes=15):
            break

        sleep_fn(max(poll_seconds, 0))

    return events
