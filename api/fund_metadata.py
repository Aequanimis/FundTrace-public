"""Small, local-only fund identity metadata helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


FUND_NAME_PATTERN = re.compile(r'var\s+fS_name\s*=\s*"([^"]+)"')


def _name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_fund_name(fund_dir: Path | str) -> str | None:
    """Return a cached public fund name without making a network request."""
    directory = Path(fund_dir)
    for filename in ("metadata.json", "_fund_manifest.json"):
        name = _name(_read_json(directory / filename).get("fund_name"))
        if name:
            return name

    for js_path in sorted(directory.glob("pingzhongdata_*.js")):
        try:
            matched = FUND_NAME_PATTERN.search(js_path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if matched:
            name = _name(matched.group(1))
            if name:
                return name
    return None


def write_fund_metadata(
    fund_dir: Path | str,
    fund_code: str,
    fund_name: str,
    *,
    source: str,
) -> Path:
    """Atomically persist the small public identity record used by the UI."""
    directory = Path(fund_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = _name(fund_name)
    if name is None:
        raise ValueError("fund_name must not be empty")
    destination = directory / "metadata.json"
    temporary = destination.with_suffix(".json.tmp")
    payload = {
        "fund_code": str(fund_code),
        "fund_name": name,
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination
