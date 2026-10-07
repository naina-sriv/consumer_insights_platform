import csv
import json
import codecs
from typing import List, Dict, Any, Tuple
from fastapi import UploadFile

def parse_and_validate_file(file: UploadFile) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses a CSV or JSON file and validates its rows.
    Returns (valid_rows, bad_rows).
    A valid row must have 'external_id' and 'text'.
    """
    valid_rows = []
    bad_rows = []
    
    content = file.file.read()
    text_content = content.decode("utf-8")
    
    lines = text_content.splitlines()
    
    if file.filename.endswith(".csv"):
        reader = csv.DictReader(lines)
        for i, row in enumerate(reader, start=1):
            if not row.get("external_id") or not row.get("text"):
                bad_rows.append({"line": i, "error": "Missing external_id or text", "data": row})
                continue
            
            metadata = {k: v for k, v in row.items() if k not in ("external_id", "text")}
            valid_rows.append({
                "external_id": str(row["external_id"]),
                "text": str(row["text"]),
                "metadata": metadata
            })
            
    elif file.filename.endswith(".json") or file.filename.endswith(".jsonl"):
        try:
            data = json.loads(text_content)
            if not isinstance(data, list):
                data = [json.loads(line) for line in lines if line.strip()]
        except json.JSONDecodeError:
            data = []
            for i, line in enumerate(lines, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    bad_rows.append({"line": i, "error": "Invalid JSON", "data": line})
                    
        for i, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                bad_rows.append({"line": i, "error": "Row is not an object", "data": item})
                continue
            if not item.get("external_id") or not item.get("text"):
                bad_rows.append({"line": i, "error": "Missing external_id or text", "data": item})
                continue
                
            metadata = item.get("metadata", {})
            if not metadata:
                metadata = {k: v for k, v in item.items() if k not in ("external_id", "text", "metadata")}
                
            valid_rows.append({
                "external_id": str(item["external_id"]),
                "text": str(item["text"]),
                "metadata": metadata
            })
    else:
        bad_rows.append({"line": 0, "error": "Unsupported file format. Use .csv or .json", "data": None})

    return valid_rows, bad_rows
