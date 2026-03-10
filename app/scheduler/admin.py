from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.scheduler.prompts import (
    JOB_DEFINITIONS_DIR,
    LEGACY_PROMPTS_DIR,
    JobPrompt,
    load_job_prompt,
    render_job_prompt,
)


@dataclass(frozen=True)
class JobDefinition:
    name: str
    path: Path
    source: str
    prompt: JobPrompt


def list_job_definitions() -> list[JobDefinition]:
    jobs: dict[str, JobDefinition] = {}
    for source, dirname in (
        ("jobs", JOB_DEFINITIONS_DIR),
        ("legacy", LEGACY_PROMPTS_DIR),
    ):
        directory = settings.workspace_dir / dirname
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.stem in jobs:
                continue
            jobs[path.stem] = JobDefinition(
                name=path.stem,
                path=path,
                source=source,
                prompt=load_job_prompt(path.stem),
            )
    return sorted(jobs.values(), key=lambda item: item.name)


def get_job_definition(name: str) -> JobDefinition | None:
    for item in list_job_definitions():
        if item.name == name:
            return item
    return None


def save_job_definition(name: str, prompt: JobPrompt) -> JobDefinition:
    jobs_dir = settings.workspace_dir / JOB_DEFINITIONS_DIR
    jobs_dir.mkdir(parents=True, exist_ok=True)
    path = jobs_dir / f"{name}.md"
    path.write_text(render_job_prompt(prompt), encoding="utf-8")
    return JobDefinition(
        name=name,
        path=path,
        source="jobs",
        prompt=prompt,
    )
