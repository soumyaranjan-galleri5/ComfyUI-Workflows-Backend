import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from src.config import settings
from src.schemas.wan import WanAnimateRequest, WanAnimateResponse
from src.services import workflow_builder
from src.services.comfyui_client import ComfyClient
from src.services.mappings import wan_animate
from src.services.param_inspector import inspect_params
from src.services.s3_upload import upload_to_s3
from src.services.workflow_runner import run_workflow
from src.utils.utils_db import log_generation_request, get_generation_by_id, update_generation_result

router = APIRouter(prefix="/wan", tags=["wan"])

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "services" / "mappings" / "registry.json"
DB_PATH = Path(__file__).resolve().parents[2] / "dummy_db" / "wan_generations.json"


@router.get("/list")
async def wan_list():
    pipelines = json.loads(REGISTRY_PATH.read_text())
    return {"pipelines": pipelines}


SLUG_TO_MAPPING = {
    "wan2-2-animate-character-swap": wan_animate,
}

SLUG_TO_SCHEMA = {
    "wan2-2-animate-character-swap": WanAnimateRequest,
}


@router.get("/{slug}/params")
async def get_params(slug: str):
    mapping = SLUG_TO_MAPPING.get(slug)
    schema = SLUG_TO_SCHEMA.get(slug)
    if not mapping or not schema:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")
    return {"params": inspect_params(schema, mapping.PARAM_META)}


@router.get("/{slug}/{generation_id}")
async def get_generation(slug: str, generation_id: str):
    """Retrieve a generation request by its ID to populate form fields."""
    if slug not in SLUG_TO_MAPPING:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    generation = get_generation_by_id(DB_PATH, slug, generation_id)
    if not generation:
        raise HTTPException(status_code=404, detail=f"Generation '{generation_id}' not found")

    return generation


@router.post("/{slug}/upload")
async def upload_file(slug: str, file: UploadFile):
    if slug not in SLUG_TO_MAPPING:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    # Define allowed file types and size limits
    ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    ALLOWED_VIDEO_TYPES = {"video/mp4"}
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp4"}
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50 MB
    MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB

    # Extract file extension
    ext = Path(file.filename).suffix.lower()

    # Validate file extension
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: PNG, JPG, JPEG, WEBP, MP4. Got: {ext}"
        )

    # Validate MIME type
    content_type = file.content_type or ""
    is_image = ext in {".png", ".jpg", ".jpeg", ".webp"}
    is_video = ext == ".mp4"

    if is_image and content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image MIME type. Expected: {ALLOWED_IMAGE_TYPES}. Got: {content_type}"
        )

    if is_video and content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid video MIME type. Expected: {ALLOWED_VIDEO_TYPES}. Got: {content_type}"
        )

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Validate file size
    max_size = MAX_IMAGE_SIZE if is_image else MAX_VIDEO_SIZE
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum: {max_mb:.0f}MB. Got: {actual_mb:.1f}MB"
        )

    # Upload to ComfyUI with a unique name to avoid collisions
    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"

    comfyui_input = Path(settings.comfyui_path) / settings.comfyui_input_folder
    comfyui_input.mkdir(parents=True, exist_ok=True)

    file_path = comfyui_input / unique_name
    file_path.write_bytes(file_content)

    # Validate video frame count if it's a video
    if is_video:
        import subprocess
        try:
            # Get frame count using ffprobe
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_packets",
                "-show_entries", "stream=nb_read_packets",
                "-of", "csv=p=0",
                str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                frame_count = int(result.stdout.strip())

                # Validate: frames <= 81
                if frame_count > 81:
                    # Clean up uploaded file
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Video has {frame_count} frames (max: 81). Please trim to 81 frames or less."
                    )

                # Validate: frames = 4n + 1 (i.e., 1, 5, 9, 13, ..., 77, 81)
                if (frame_count - 1) % 4 != 0:
                    # Calculate nearest valid frame counts
                    n_lower = (frame_count - 1) // 4
                    n_upper = n_lower + 1
                    valid_lower = 4 * n_lower + 1
                    valid_upper = 4 * n_upper + 1

                    # Only show valid_upper if it's <= 81
                    if valid_upper <= 81:
                        suggestion = f"{valid_lower} or {valid_upper}"
                    else:
                        suggestion = f"{valid_lower}"

                    # Clean up uploaded file
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Video has {frame_count} frames. Frame count must be of the form 4k+1. Valid counts: {suggestion}. Please trim your video."
                    )

                print(f"[UPLOAD] Video validation passed: {frame_count} frames (valid: ≤81 and 4n+1 format)")
        except subprocess.TimeoutExpired:
            # If ffprobe times out, just log and continue (don't block upload)
            print(f"[UPLOAD] Warning: ffprobe timeout for {unique_name}, skipping frame validation")
        except HTTPException:
            # Re-raise HTTP exceptions (validation errors)
            raise
        except Exception as e:
            # If frame validation fails for any other reason, log but don't block upload
            print(f"[UPLOAD] Warning: Could not validate frames for {unique_name}: {e}")

    # Upload to S3 and get preview URL
    content_type = file.content_type or "application/octet-stream"
    try:
        s3_url = await upload_to_s3(file_path, content_type)
    except Exception as e:
        # If S3 upload fails, still return the filename
        s3_url = None

    return {
        "filename": unique_name,
        "preview_url": s3_url
    }


@router.post("/{slug}", response_model=WanAnimateResponse)
async def generate_video(slug: str, request: WanAnimateRequest):
    mapping = SLUG_TO_MAPPING.get(slug)
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    # Get params and run pre_build to get final parameters
    params = request.model_dump()

    print("\n" + "="*80)
    print("🎬 WAN GENERATION STARTED")
    print("="*80)
    print("\n📥 PARAMS FROM FRONTEND (before pre_build):")
    import json
    import pprint
    pprint.pprint(params, width=120, sort_dicts=False)

    if mapping.pre_build:
        try:
            params = mapping.pre_build(params)
        except ValueError as e:
            # Validation error from pre_build (e.g., invalid video frame count)
            raise HTTPException(status_code=400, detail=str(e))

    print("\n✨ PARAMS AFTER PRE_BUILD (modified):")
    pprint.pprint(params, width=120, sort_dicts=False)

    # Log the generation request with MODIFIED parameters (after pre_build)
    generation_id = log_generation_request(DB_PATH, slug, params)

    workflow = workflow_builder.build(
        params=params,
        param_map=mapping.PARAM_MAP,
        template_path=mapping.TEMPLATE,
        pre_build=None,  # Already ran pre_build above
        post_build=mapping.post_build if hasattr(mapping, 'post_build') else None,
    )

    print("\n🔧 WORKFLOW NODES (after param injection):")
    # Get all nodes that were modified by param injection
    injected_node_ids = set(node_id for node_id, _ in mapping.PARAM_MAP.values())
    print(f"  Showing {len(injected_node_ids)} nodes with injected parameters: {sorted(injected_node_ids)}\n")

    for node_id in sorted(injected_node_ids, key=int):
        if node_id in workflow:
            print(f"\n  Node {node_id} - {workflow[node_id].get('class_type', 'Unknown')}:")
            pprint.pprint(workflow[node_id].get('inputs', {}), width=120, indent=4)
    print("\n" + "="*80 + "\n")

    try:
        results = await run_workflow(workflow)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    output_urls = [result["s3_url"] for result in results if "s3_url" in result]

    # Extract metadata from results (already extracted in workflow_runner)
    output_metadata = []
    for result in results:
        metadata = result.get("metadata")
        if metadata:
            print(f"[WAN] Metadata for {result.get('filename')}: {metadata}")
            output_metadata.append(metadata)
        else:
            print(f"[WAN] No metadata for {result.get('filename')}")
            output_metadata.append({})

    # Update the generation record with the results
    update_generation_result(DB_PATH, generation_id, output_urls, "completed")

    return WanAnimateResponse(
        status="completed",
        output_urls=output_urls,
        output_metadata=output_metadata,
        message=f"Generated {len(results)} output(s)",
        generation_id=generation_id,
    )
