"""CLI entrypoint for aviation preflight assistant skill."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aviation_preflight.briefing import (  # noqa: E402
    generate_preflight_brief,
    parse_iso_datetime,
    render_brief_markdown,
)
from aviation_preflight.providers import AviationDataProvider  # noqa: E402
from aviation_preflight.scheduler import WatchEvent, run_watch_loop  # noqa: E402


def _load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate aviation preflight briefings.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    brief_parser = subparsers.add_parser("brief", help="Generate a single briefing.")
    brief_parser.add_argument("--plan", required=True, type=Path, help="Path to flight plan JSON.")
    brief_parser.add_argument("--output", type=Path, help="Markdown output path.")
    brief_parser.add_argument("--json-output", type=Path, help="JSON output path.")
    brief_parser.add_argument(
        "--references-dir",
        type=Path,
        help="Optional override for references directory.",
    )
    brief_parser.add_argument(
        "--simulate-now",
        type=str,
        help="Optional ISO datetime for deterministic run.",
    )

    watch_parser = subparsers.add_parser("watch", help="Watch and auto-emit T-2h/T-1h briefings.")
    watch_parser.add_argument("--plan", required=True, type=Path, help="Path to flight plan JSON.")
    watch_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".briefings"),
        help="Directory where briefing snapshots will be saved.",
    )
    watch_parser.add_argument(
        "--references-dir",
        type=Path,
        help="Optional override for references directory.",
    )
    watch_parser.add_argument("--poll-seconds", type=int, default=300, help="Polling cadence.")
    watch_parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Safety stop for local test runs. 0 means until completion.",
    )
    return parser


def run_brief_command(args: argparse.Namespace) -> int:
    plan = _load_plan(args.plan)
    now = parse_iso_datetime(args.simulate_now) if args.simulate_now else datetime.now(UTC)
    provider = AviationDataProvider()
    brief = generate_preflight_brief(
        plan=plan,
        provider=provider,
        references_dir=args.references_dir,
        now=now,
    )
    markdown = render_brief_markdown(brief)

    if args.output:
        _write_text(args.output, markdown)
    else:
        print(markdown)

    if args.json_output:
        _write_json(args.json_output, brief)
    return 0


def run_watch_command(args: argparse.Namespace) -> int:
    plan = _load_plan(args.plan)
    provider = AviationDataProvider()
    departure_time = parse_iso_datetime(str(plan["departure_time"]))
    offsets = plan.get("auto_brief_offsets_min", [120, 60])

    def generate(now: datetime) -> dict:
        return generate_preflight_brief(
            plan=plan,
            provider=provider,
            references_dir=args.references_dir,
            now=now,
        )

    def emit(event: WatchEvent) -> None:
        stamp = event.emitted_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        file_stem = f"{stamp}_{event.label}_{event.event_type}".replace(" ", "_")
        markdown = render_brief_markdown(event.briefing)
        markdown = f"<!-- {event.event_type} {event.label} -->\n\n" + markdown
        _write_text(args.output_dir / f"{file_stem}.md", markdown)
        _write_json(args.output_dir / f"{file_stem}.json", event.briefing)
        print(f"Emitted {event.event_type} brief: {file_stem}")

    def now_fn() -> datetime:
        return datetime.now(UTC)

    events = run_watch_loop(
        departure_time=departure_time,
        offsets_min=[int(item) for item in offsets],
        generate_fn=generate,
        emit_fn=emit,
        now_fn=now_fn,
        sleep_fn=time.sleep,
        poll_seconds=args.poll_seconds,
        max_iterations=args.max_iterations,
    )
    print(f"Watch loop finished. Events emitted: {len(events)}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "brief":
        return run_brief_command(args)
    if args.command == "watch":
        return run_watch_command(args)
    parser.error("Unknown command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
