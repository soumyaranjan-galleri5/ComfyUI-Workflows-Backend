from pathlib import Path
from typing import Union

import httpx

from src.config import settings


async def upload_to_s3(
    file_source: Union[Path, bytes],
    content_type: str = "application/octet-stream",
    filename: str = None
) -> str:
    """
    Upload a file or bytes to the storage endpoint and return the public URL.

    Args:
        file_source: Path to file or bytes content
        content_type: MIME type of the file
        filename: Required if file_source is bytes, optional if Path

    Returns:
        S3 public URL

    Examples:
        # Upload from file path
        url = await upload_to_s3(Path("video.mp4"), "video/mp4")

        # Upload from bytes (no disk write)
        url = await upload_to_s3(file_bytes, "video/mp4", filename="output.mp4")
    """
    if isinstance(file_source, bytes):
        # Upload from bytes directly (no disk write needed)
        if not filename:
            raise ValueError("filename is required when uploading bytes")
        file_bytes = file_source
        file_name = filename
    else:
        # Upload from file path (existing behavior)
        file_bytes = file_source.read_bytes()
        file_name = file_source.name

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            settings.s3_url_endpoint,
            files={"file": (file_name, file_bytes, content_type)},
            headers={"x-api-key": settings.s3_api_key},
        )
    response.raise_for_status()
    result = response.json()

    url = result.get("s3_url", "")
    if not url:
        raise RuntimeError("S3 upload succeeded but no URL returned")

    return url
