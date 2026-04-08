import logging
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


async def upload_to_s3(file_path: Path, content_type: str = "application/octet-stream") -> str:
    """Upload a file to the storage endpoint and return the public URL."""
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            settings.s3_url_endpoint,
            files={"file": (file_path.name, file_path.read_bytes(), content_type)},
            headers={"x-api-key": settings.s3_api_key},
        )
    response.raise_for_status()
    result = response.json()

    url = result.get("s3_url", "")
    logger.info("Uploaded %s -> %s", file_path.name, url)
    return url
