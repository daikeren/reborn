from __future__ import annotations

import re

import yaml

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown string.

    Returns (metadata_dict, body_text).  If no frontmatter is found,
    metadata_dict is empty and body_text is the original text.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    body = text[m.end() :]
    return meta, body
