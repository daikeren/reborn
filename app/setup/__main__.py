from __future__ import annotations

import argparse
from pathlib import Path

from .engine import SetupAnswers, apply_setup, emit_json, inspect_setup, verify_setup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reborn setup tooling")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inspect", help="Inspect current setup state")

    apply_parser = sub.add_parser("apply", help="Apply setup answers")
    apply_parser.add_argument(
        "--answers-file",
        type=Path,
        required=True,
        help="Path to a JSON file matching the setup answers schema",
    )
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render planned changes without writing files",
    )

    sub.add_parser("verify", help="Verify setup readiness")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inspect":
        emit_json(inspect_setup().to_dict())
        return
    if args.command == "apply":
        answers = SetupAnswers.from_json_file(args.answers_file)
        emit_json(apply_setup(answers, dry_run=args.dry_run))
        return
    if args.command == "verify":
        emit_json(verify_setup())
        return
    parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
