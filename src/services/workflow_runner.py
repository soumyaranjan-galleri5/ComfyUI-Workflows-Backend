import base64
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from src.config import settings
from src.exceptions import (
    InvalidURLError,
    FileTypeMismatchError,
    DownloadError
)
from src.services.comfyui_client import ComfyClient
from src.services.s3_upload import upload_to_s3

logger = logging.getLogger(__name__)


def _is_base64(value: str) -> bool:
    if value.startswith("data:"):
        return True
    if len(value) < 64:
        return False
    try:
        base64.b64decode(value, validate=True)
        return True
    except Exception:
        return False


def _decode_base64(value: str) -> bytes:
    if value.startswith("data:") and ";base64," in value:
        value = value.split(";base64,", 1)[1]
    return base64.b64decode(value)


def _ext_from_url(url: str) -> str:
    path_part = url.split("?")[0].split("/")[-1]
    ext = Path(path_part).suffix
    return ext if ext else ".bin"


async def _download_url(url: str, save_dir: Path) -> Path:
    """Download URL and validate file type."""
    # Validate URL extension
    ext = _ext_from_url(url)
    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mp3", ".wav"}
    if ext not in allowed_extensions:
        raise InvalidURLError(url, f"Unsupported file type: {ext}")

    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"dl_{uuid.uuid4().hex[:8]}{ext}"

    # Download file
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(url)
        response.raise_for_status()
        file_content = response.content
    except httpx.HTTPError as e:
        raise DownloadError(url, str(e))

    # Validate MIME type using magic bytes
    try:
        import magic
        detected_mime = magic.from_buffer(file_content, mime=True)

        # Define expected MIME types for each extension
        valid_mimes = {
            ".png": ["image/png"],
            ".jpg": ["image/jpeg"],
            ".jpeg": ["image/jpeg"],
            ".webp": ["image/webp"],
            ".mp4": ["video/mp4"],
            ".mp3": ["audio/mpeg"],
            ".wav": ["audio/wav", "audio/x-wav"]
        }

        expected = valid_mimes.get(ext, [])
        if detected_mime not in expected:
            raise FileTypeMismatchError(
                filename=url.split("/")[-1],
                expected=", ".join(expected),
                actual=detected_mime
            )

        logger.info("URL validation passed: %s (%s)", url, detected_mime)
    except ImportError:
        logger.warning("python-magic not installed, skipping URL MIME validation")

    # Save validated content
    save_path.write_bytes(file_content)
    logger.info("Downloaded %s -> %s", url, save_path)
    return save_path


async def resolve_and_upload(
    client: ComfyClient, value: str, save_dir: Path
) -> str:
    """
    Resolve a URL, base64, or file path to a ComfyUI-local filename.

    Raises:
        InvalidURLError: If URL is malformed or has invalid protocol
        FileTypeMismatchError: If file type doesn't match extension
        DownloadError: If download fails
    """
    if not isinstance(value, str) or not value:
        return value

    # Detect URL-like strings (including malformed ones like htts://)
    if "://" in value:
        # Strict protocol validation - only HTTPS allowed
        if not value.startswith("https://"):
            raise InvalidURLError(value, "Only HTTPS protocol is supported")

        # Download and validate URL
        file_path = await _download_url(value, save_dir)
        return await client.upload_file(str(file_path))

    if _is_base64(value):
        ext = ".png"
        if value.startswith("data:"):
            mime = value.split(";")[0].split(":")[1]
            ext_map = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/webp": ".webp",
                "video/mp4": ".mp4",
                "audio/mpeg": ".mp3",
                "audio/wav": ".wav",
            }
            ext = ext_map.get(mime, ".bin")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"b64_{uuid.uuid4().hex[:8]}{ext}"
        save_path.write_bytes(_decode_base64(value))
        logger.info("Decoded base64 -> %s", save_path)
        return await client.upload_file(str(save_path))

    # Already a filename in ComfyUI input folder
    return value


def _safe_unlink(path: Path, label: str) -> None:
    """Delete a file, logging (not raising) on failure so cleanup loops continue."""
    try:
        if path.exists():
            path.unlink()
            logger.info("Cleaned up ComfyUI %s: %s", label, path)
    except OSError as e:
        logger.warning("Failed to delete ComfyUI %s %s: %s", label, path, e)


def _cleanup_comfyui_files(input_files: list[str], output_files: list[dict]):
    """Delete uploaded inputs and generated outputs from ComfyUI folders."""
    comfyui_base = Path(settings.comfyui_path)

    # Clean input files
    for filename in input_files:
        _safe_unlink(comfyui_base / settings.comfyui_input_folder / filename, "input")

    # Clean output files
    for file_info in output_files:
        filename = file_info["filename"]
        subfolder = file_info.get("subfolder", "")
        candidates = [
            comfyui_base / settings.comfyui_output_folder / subfolder / filename,
            comfyui_base / settings.comfyui_output_folder / filename,
            comfyui_base / "video" / subfolder / filename,
            comfyui_base / "video" / filename,
        ]
        for path in candidates:
            _safe_unlink(path, "output")


async def run_workflow(workflow: dict[str, Any]) -> list[dict]:
    """Run a ComfyUI workflow: resolve inputs, execute, upload to S3, cleanup."""
    client = ComfyClient()
    if not await client.check_connection():
        raise ConnectionError("Cannot connect to ComfyUI")

    uploaded_input_files: list[str] = []
    all_output_file_infos: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="comfy_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        try:
            # Resolve media inputs (URL/base64 -> temp dir -> upload to ComfyUI)
            #
            # NOTE: Some ComfyUI nodes support direct URL loading without download/upload:
            # - VHS_LoadVideoPath: Supports URLs, downloads automatically (has is_url() check)
            # - LoadVideoPath: Supports URLs, downloads automatically
            # - LoadImagePath: Supports URLs, downloads automatically
            #
            # Current workflows use upload-type nodes (VHS_LoadVideo, LoadImage) which require
            # files to be in ComfyUI/input folder. To eliminate this download->upload step:
            # 1. Change workflow JSON: VHS_LoadVideo → VHS_LoadVideoPath
            # 2. Pass S3 URLs directly (skip resolve_and_upload)
            # 3. Node will download from URL automatically
            #
            # For now, we download S3 → temp → upload to ComfyUI for compatibility.
            for node_id, node in workflow.items():
                class_type = node.get("class_type", "")
                inputs = node.get("inputs", {})

                if class_type == "LoadImage":
                    raw = inputs.get("image", "")
                    filename = await resolve_and_upload(client, raw, tmp_path)
                    node["inputs"]["image"] = filename
                    if filename != raw:
                        uploaded_input_files.append(filename)
                elif class_type == "VHS_LoadVideo":
                    raw = inputs.get("video", "")
                    filename = await resolve_and_upload(client, raw, tmp_path)
                    node["inputs"]["video"] = filename
                    if filename != raw:
                        uploaded_input_files.append(filename)
                elif class_type == "LoadAudio":
                    raw = inputs.get("audio", "")
                    if raw:
                        filename = await resolve_and_upload(client, raw, tmp_path)
                        node["inputs"]["audio"] = filename
                        if filename != raw:
                            uploaded_input_files.append(filename)

            # Queue and wait
            prompt_id = await client.queue_prompt(workflow)
            history = await client.wait_for_completion(prompt_id)

            # Collect outputs
            all_outputs = client.get_outputs(history)

            results = []
            for node_id, files in all_outputs.items():
                for file_info in files:
                    filename = file_info["filename"]
                    subfolder = file_info.get("subfolder", "")
                    file_type = file_info.get("type", "output")
                    media_type = file_info.get("media_type", "unknown")

                    all_output_file_infos.append(file_info)

                    # Download output to temp dir
                    file_bytes = await client.download_output_file(
                        filename, subfolder, file_type
                    )
                    local_path = tmp_path / filename
                    local_path.write_bytes(file_bytes)

                    # Extract metadata for videos before uploading
                    metadata = None
                    if media_type == "video":
                        from ..utils.utils_video import get_video_metadata
                        metadata = get_video_metadata(local_path)

                    # Upload to S3
                    content_type = "video/mp4" if media_type == "video" else "image/png"
                    s3_url = await upload_to_s3(local_path, content_type)

                    logger.info(
                        "Output: node=%s file=%s -> %s",
                        node_id,
                        filename,
                        s3_url,
                    )
                    results.append(
                        {
                            "node_id": node_id,
                            "filename": filename,
                            "media_type": media_type,
                            "s3_url": s3_url,
                            "metadata": metadata,
                            "size_bytes": len(file_bytes),
                        }
                    )

            return results

        finally:
            # Always cleanup ComfyUI files, even if workflow execution fails
            logger.info("Cleaning up ComfyUI files (inputs: %d, outputs: %d)",
                       len(uploaded_input_files), len(all_output_file_infos))
            _cleanup_comfyui_files(uploaded_input_files, all_output_file_infos)

    # temp dir auto-deleted here
