from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.request import urlopen

SKILL_NAME = "reborn-setup"
RAW_SKILL_URL = (
    "https://raw.githubusercontent.com/daikeren/reborn/main/bootstrap/"
    "reborn-setup/SKILL.md"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def skill_source() -> Path:
    return repo_root() / "bootstrap" / SKILL_NAME / "SKILL.md"


def skill_contents() -> str:
    source = skill_source()
    if source.exists():
        return source.read_text(encoding="utf-8")
    with urlopen(RAW_SKILL_URL, timeout=15) as response:
        return response.read().decode("utf-8")


def default_skill_dirs(home: Path | None = None) -> list[Path]:
    base = home or Path.home()
    codex_home_raw = os.getenv("CODEX_HOME")
    dirs: list[Path] = []
    if codex_home_raw:
        codex_home = Path(codex_home_raw).expanduser()
        dirs.append(codex_home / "skills")
    else:
        dirs.append(base / ".codex" / "skills")
    dirs.append(base / ".claude" / "skills")
    return dirs


def resolve_destinations(
    *, destination: Path | None = None, tool: str = "auto", home: Path | None = None
) -> list[Path]:
    if destination is not None:
        return [destination.expanduser().resolve()]

    dirs = default_skill_dirs(home)
    if tool == "codex":
        return [dirs[0]]
    if tool == "claude":
        return [dirs[1]]
    if tool == "both":
        return dirs

    existing = [path for path in dirs if path.parent.exists() or path.exists()]
    return existing or [dirs[0]]


def install_skill(destination: Path) -> Path:
    target_dir = destination / SKILL_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "SKILL.md").write_text(skill_contents(), encoding="utf-8")
    return target_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the Reborn bootstrap skill")
    parser.add_argument(
        "--destination",
        type=Path,
        help="Install into this exact skills directory instead of autodetecting",
    )
    parser.add_argument(
        "--tool",
        choices=("auto", "codex", "claude", "both"),
        default="auto",
        help="Which local skill directory to target when --destination is omitted",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    installed_paths: list[Path] = []
    for destination in resolve_destinations(
        destination=args.destination, tool=args.tool
    ):
        installed_paths.append(install_skill(destination))

    print("Installed Reborn Setup skill:")
    for path in installed_paths:
        print(f"- {path}")
    print("")
    print("Invoke it from Codex/Claude Code as: Reborn Setup")


if __name__ == "__main__":
    main()
