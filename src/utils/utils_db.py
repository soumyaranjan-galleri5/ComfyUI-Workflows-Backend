"""Simple JSON database utility for logging generation requests."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def log_generation_request(db_path: Path, slug: str, request_data: Dict[str, Any]) -> str:
    """Log a generation request to the JSON database.

    Args:
        db_path: Path to the JSON database file
        slug: The workflow slug (e.g., 'wan2-2-animate-character-swap')
        request_data: The request parameters to log

    Returns:
        The generated generation_id
    """
    # Ensure the database file exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.write_text("[]")

    # Read existing data
    try:
        data = json.loads(db_path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        data = []

    # Create new record
    generation_id = str(uuid.uuid4())
    record = {
        "generation_id": generation_id,
        "slug": slug,
        "request": request_data,
        "created_at": datetime.utcnow().isoformat(),
    }

    # Append and save
    data.append(record)
    db_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return generation_id


def get_generation_by_id(db_path: Path, slug: str, generation_id: str) -> Dict[str, Any] | None:
    """Retrieve a generation request by its ID.

    Args:
        db_path: Path to the JSON database file
        slug: The workflow slug
        generation_id: The generation ID to retrieve

    Returns:
        The generation record if found, None otherwise
    """
    if not db_path.exists():
        return None

    try:
        data = json.loads(db_path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return None

    # Find the record
    for record in data:
        if record.get("generation_id") == generation_id and record.get("slug") == slug:
            return record

    return None


def update_generation_result(db_path: Path, generation_id: str, output_urls: list[str], status: str = "completed") -> bool:
    """Update a generation record with the result.

    Args:
        db_path: Path to the JSON database file
        generation_id: The generation ID to update
        output_urls: List of output URLs
        status: Status of the generation

    Returns:
        True if updated successfully, False otherwise
    """
    if not db_path.exists():
        return False

    try:
        data = json.loads(db_path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return False

    # Find and update the record
    updated = False
    for record in data:
        if record.get("generation_id") == generation_id:
            record["output_urls"] = output_urls
            record["status"] = status
            record["completed_at"] = datetime.utcnow().isoformat()
            updated = True
            break

    if updated:
        db_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return updated
