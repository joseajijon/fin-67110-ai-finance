#!/usr/bin/env python3
"""Block completion when a declared skill report has unsupported numbers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


DECLARATION = re.compile(r"SKILL_OUTPUT:\s*(.+?)(?:\n|$)")
NUMBER = re.compile(r"(?<![A-Za-z])(?:\$?\d[\d,]*(?:\.\d+)?%?)")
MARKER = re.compile(r"<!--\s*evidence:([A-Za-z0-9_.-]+)\s*-->")
VALID_TYPES = {"filing", "fact", "computation", "config"}


def check(report_path: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = report_path.with_suffix(report_path.suffix + ".evidence.json")
    if not report_path.is_file():
        return [f"Skill output does not exist: {report_path}"]
    if not manifest_path.is_file():
        return [f"Evidence manifest does not exist: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read evidence manifest: {exc}"]
    entries = manifest.get("evidence", [])
    evidence = {str(item.get("id", "")): item for item in entries if isinstance(item, dict)}
    for evidence_id, item in evidence.items():
        source_type = item.get("type")
        if not evidence_id or source_type not in VALID_TYPES:
            errors.append(f"Invalid evidence entry: {item}")
            continue
        required = {
            "filing": ("filing", "section", "date", "source"),
            "fact": ("facts_file", "key"),
            "computation": ("expression", "inputs"),
            "config": ("config_file", "key"),
        }[source_type]
        missing = [field for field in required if item.get(field) in (None, "", [])]
        if missing:
            errors.append(f"Evidence {evidence_id} lacks: {', '.join(missing)}")
    for line_number, line in enumerate(report_path.read_text(encoding="utf-8").splitlines(), 1):
        if not NUMBER.search(line):
            continue
        markers = MARKER.findall(line)
        if not markers:
            errors.append(f"Line {line_number} has a number without evidence: {line}")
            continue
        unknown = [marker for marker in markers if marker not in evidence]
        if unknown:
            errors.append(f"Line {line_number} uses unknown evidence: {', '.join(unknown)}")
    return errors


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    message = str(payload.get("last_assistant_message", ""))
    match = DECLARATION.search(message)
    if not match:
        print(json.dumps({"systemMessage": "No SKILL_OUTPUT declaration; evidence hook skipped."}))
        return 0
    report_path = Path(match.group(1).strip()).expanduser().resolve()
    errors = check(report_path)
    if errors:
        reason = "Skill-output evidence check failed:\n" + "\n".join(f"- {item}" for item in errors)
        print(json.dumps({"decision": "block", "reason": reason}))
    else:
        print(json.dumps({"systemMessage": f"Evidence check passed: {report_path}"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
