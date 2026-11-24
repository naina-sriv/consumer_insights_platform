import csv
import io
import json
import logging
from typing import Any
from fastapi import UploadFile

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".csv", ".json", ".jsonl")


def _clean_str(val: Any) -> str:
    """Safely convert value to trimmed string."""
    if val is None:
        return ""
    return str(val).strip()


def parse_and_validate_file(
    file: UploadFile,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse and validate uploaded tabular / semi-structured consumer feedback file.

    Supports UTF-8 / UTF-8-BOM encoded CSV, JSON (array of objects), and JSON Lines.
    Enforces required fields: 'external_id' and 'text'.
    Gathers additional fields into 'metadata' dictionary.
    Deduplicates external_id in the file to prevent downstream DB constraint failures.

    Returns:
        (valid_rows, bad_rows)
    """
    filename = (file.filename or "").lower()

    if not any(filename.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        return [], [
            {
                "line": 0,
                "error": "Unsupported file format. Must be .csv, .json, or .jsonl",
                "data": None,
            }
        ]

    # Read binary content and decode using utf-8-sig to automatically strip BOM
    raw_bytes = file.file.read()
    try:
        text_content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [], [{"line": 0, "error": f"Encoding error: file must be UTF-8 encoded ({exc})", "data": None}]

    valid_rows: list[dict[str, Any]] = []
    bad_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    if filename.endswith(".csv"):
        # Stream parse with csv.DictReader
        stream = io.StringIO(text_content, newline="")
        reader = csv.DictReader(stream)

        # Normalize column header names
        if reader.fieldnames:
            reader.fieldnames = [name.strip() if name else "" for name in reader.fieldnames]

        for line_num, row in enumerate(reader, start=2):  # start=2 accounts for header row
            if not row or all(v is None or not str(v).strip() for v in row.values()):
                continue  # Skip trailing empty lines

            ext_id = _clean_str(row.get("external_id"))
            text = _clean_str(row.get("text"))

            if not ext_id or not text:
                bad_rows.append({
                    "line": line_num,
                    "error": "Missing required field 'external_id' or 'text'",
                    "data": row,
                })
                continue

            if ext_id in seen_ids:
                bad_rows.append({
                    "line": line_num,
                    "error": f"Duplicate external_id '{ext_id}' in file",
                    "data": row,
                })
                continue

            seen_ids.add(ext_id)
            metadata = {
                k: v for k, v in row.items()
                if k not in ("external_id", "text") and k != ""
            }

            valid_rows.append({
                "external_id": ext_id,
                "text": text,
                "metadata": metadata,
            })

    elif filename.endswith((".json", ".jsonl")):
        # Check if entire content is a JSON array
        is_json_array = False
        parsed_items: list[tuple[int, Any]] = []

        stripped = text_content.strip()
        if stripped.startswith("["):
            try:
                data = json.loads(stripped)
                if isinstance(data, list):
                    is_json_array = True
                    parsed_items = list(enumerate(data, start=1))
            except json.JSONDecodeError:
                pass

        if not is_json_array:
            # Parse as JSON Lines (one JSON object per line)
            for line_num, line in enumerate(text_content.splitlines(), start=1):
                clean_line = line.strip()
                if not clean_line:
                    continue
                try:
                    obj = json.loads(clean_line)
                    parsed_items.append((line_num, obj))
                except json.JSONDecodeError:
                    bad_rows.append({
                        "line": line_num,
                        "error": "Invalid JSON syntax",
                        "data": clean_line[:120],
                    })

        for line_num, item in parsed_items:
            if not isinstance(item, dict):
                bad_rows.append({
                    "line": line_num,
                    "error": "Row must be a JSON object",
                    "data": str(item)[:120],
                })
                continue

            ext_id = _clean_str(item.get("external_id"))
            text = _clean_str(item.get("text"))

            if not ext_id or not text:
                bad_rows.append({
                    "line": line_num,
                    "error": "Missing required field 'external_id' or 'text'",
                    "data": item,
                })
                continue

            if ext_id in seen_ids:
                bad_rows.append({
                    "line": line_num,
                    "error": f"Duplicate external_id '{ext_id}' in file",
                    "data": item,
                })
                continue

            seen_ids.add(ext_id)
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {
                    k: v for k, v in item.items()
                    if k not in ("external_id", "text", "metadata")
                }

            valid_rows.append({
                "external_id": ext_id,
                "text": text,
                "metadata": metadata,
            })

    return valid_rows, bad_rows
