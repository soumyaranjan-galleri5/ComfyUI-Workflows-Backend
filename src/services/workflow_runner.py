import base64
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from src.config import settings
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
    save_dir.mkdir(parents=True, exist_ok=True)
    ext = _ext_from_url(url)
    save_path = save_dir / f"dl_{uuid.uuid4().hex[:8]}{ext}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
    response.raise_for_status()
    save_path.write_bytes(response.content)
    logger.info("Downloaded %s -> %s", url, save_path)
    return save_path


async def resolve_and_upload(
    client: ComfyClient, value: str, save_dir: Path
) -> str:
    """Resolve a URL, base64, or file path to a ComfyUI-local filename."""
    if not isinstance(value, str) or not value:
        return value

    if value.startswith("http://") or value.startswith("https://"):
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


def _cleanup_comfyui_files(input_files: list[str], output_files: list[dict]):
    """Delete uploaded inputs and generated outputs from ComfyUI folders."""
    comfyui_base = Path(settings.comfyui_path)

    # Clean input files
    for filename in input_files:
        path = comfyui_base / settings.comfyui_input_folder / filename
        if path.exists():
            path.unlink()
            logger.info("Cleaned up ComfyUI input: %s", path)

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
            if path.exists():
                path.unlink()
                logger.info("Cleaned up ComfyUI output: %s", path)


async def run_workflow(workflow: dict[str, Any]) -> list[dict]:
    """Run a ComfyUI workflow: resolve inputs, execute, upload to S3, cleanup."""
    client = ComfyClient()
    if not await client.check_connection():
        raise ConnectionError("Cannot connect to ComfyUI")

    uploaded_input_files: list[str] = []
    all_output_file_infos: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="comfy_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Resolve media inputs (URL/base64 -> temp dir -> upload to ComfyUI)
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

        # Cleanup ComfyUI input and output folders
        _cleanup_comfyui_files(uploaded_input_files, all_output_file_infos)

    # temp dir auto-deleted here
    return results
