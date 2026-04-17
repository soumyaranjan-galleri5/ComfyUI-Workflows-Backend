import json
import uuid
from pathlib import Path

import magic
from fastapi import APIRouter, HTTPException, Request, UploadFile

from src.config import settings
from src.exceptions import WorkflowError
from src.schemas.wan import (
    WanAnimateRequest,
    WanVaceRequest,
    WanAnimateResponse,
    WanVaceResponse
)
from src.services import workflow_builder
from src.services.comfyui_client import ComfyClient
from src.services.mappings import wan_animate, wan_vace_mask_edit
from src.services.param_inspector import inspect_params
from src.services.s3_upload import upload_to_s3
from src.services.workflow_runner import run_workflow
from src.utils.utils_db import (
    log_generation_request,
    get_generation_by_id,
    update_generation_result
)

router = APIRouter(prefix="/wan", tags=["wan"])

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "services" / "mappings" / "registry.json"
DB_PATH = Path(__file__).resolve().parents[2] / "dummy_db" / "wan_generations.json"

# Mapping configuration
SLUG_TO_MAPPING = {
    "wan2-2-animate-character-swap": wan_animate,
    "wan2-2-fun-vace-mask-edit-controlnet": wan_vace_mask_edit,
}


################################################################################
#                    WAN ANIMATE WORKFLOW ROUTE                                #
################################################################################

@router.post("/wan2-2-animate-character-swap", response_model=WanAnimateResponse)
async def generate_wan_animate(request: WanAnimateRequest):
    """Generate video using WAN 2.2 Animate Character Swap workflow."""
    slug = "wan2-2-animate-character-swap"
    mapping = wan_animate
    params = request.model_dump()

    print("\n" + "="*80)
    print(f"🎬 WAN GENERATION STARTED: {slug}")
    print("="*80)
    print("\n📥 PARAMS FROM FRONTEND (before pre_build):")
    import pprint
    pprint.pprint(params, width=120, sort_dicts=False)

    # Run pre_build validation and transformation
    if mapping.pre_build:
        try:
            params = mapping.pre_build(params)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    print("\n✨ PARAMS AFTER PRE_BUILD (modified):")
    pprint.pprint(params, width=120, sort_dicts=False)

    # Log the generation request
    generation_id = log_generation_request(DB_PATH, slug, params)

    # Build workflow from template
    workflow_subdir = getattr(mapping, "WORKFLOW_SUBDIR", "")
    template_path = f"{workflow_subdir}/{mapping.TEMPLATE}" if workflow_subdir else mapping.TEMPLATE

    workflow = workflow_builder.build(
        params=params,
        param_map=mapping.PARAM_MAP,
        template_path=template_path,
        pre_build=None,
        post_build=mapping.post_build if hasattr(mapping, 'post_build') else None,
    )

    # Debug: Show injected workflow nodes
    print("\n🔧 WORKFLOW NODES (after param injection):")
    injected_node_ids = set(node_id for node_id, _ in mapping.PARAM_MAP.values())
    print(f"  Showing {len(injected_node_ids)} nodes with injected parameters: {sorted(injected_node_ids)}\n")

    for node_id in sorted(injected_node_ids, key=int):
        if node_id in workflow:
            print(f"\n  Node {node_id} - {workflow[node_id].get('class_type', 'Unknown')}:")
            pprint.pprint(workflow[node_id].get('inputs', {}), width=120, indent=4)
    print("\n" + "="*80 + "\n")

    # Execute workflow
    try:
        results = await run_workflow(workflow)
    except WorkflowError as e:
        # Custom workflow errors with user-friendly messages
        raise HTTPException(status_code=400, detail=e.user_message)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail="Service unavailable: Cannot connect to ComfyUI")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail="Request timeout: Workflow took too long")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail="Workflow execution failed")
    except Exception as e:
        # Unexpected errors
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

    # Extract output URLs and metadata
    output_urls = [result["s3_url"] for result in results if "s3_url" in result]
    output_metadata = []
    for result in results:
        metadata = result.get("metadata")
        if metadata:
            print(f"[WAN] Metadata for {result.get('filename')}: {metadata}")
            output_metadata.append(metadata)
        else:
            print(f"[WAN] No metadata for {result.get('filename')}")
            output_metadata.append({})

    # Update generation record
    update_generation_result(DB_PATH, generation_id, output_urls, "completed")

    return WanAnimateResponse(
        status="completed",
        output_urls=output_urls,
        output_metadata=output_metadata,
        message=f"Generated {len(results)} output(s)",
        generation_id=generation_id,
    )


################################################################################
#                    WAN VACE WORKFLOW ROUTE                                   #
################################################################################

@router.post("/wan2-2-fun-vace-mask-edit-controlnet", response_model=WanVaceResponse)
async def generate_wan_vace(request: WanVaceRequest):
    """Generate video using WAN 2.2 Fun VACE Mask Edit workflow."""
    slug = "wan2-2-fun-vace-mask-edit-controlnet"
    mapping = wan_vace_mask_edit
    params = request.model_dump()

    print("\n" + "="*80)
    print(f"🎬 WAN GENERATION STARTED: {slug}")
    print("="*80)
    print("\n📥 PARAMS FROM FRONTEND (before pre_build):")
    import pprint
    pprint.pprint(params, width=120, sort_dicts=False)

    # Run pre_build validation and transformation
    if mapping.pre_build:
        try:
            params = mapping.pre_build(params)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    print("\n✨ PARAMS AFTER PRE_BUILD (modified):")
    pprint.pprint(params, width=120, sort_dicts=False)

    # Log the generation request
    generation_id = log_generation_request(DB_PATH, slug, params)

    # Build workflow from template
    workflow_subdir = getattr(mapping, "WORKFLOW_SUBDIR", "")
    template_path = f"{workflow_subdir}/{mapping.TEMPLATE}" if workflow_subdir else mapping.TEMPLATE

    workflow = workflow_builder.build(
        params=params,
        param_map=mapping.PARAM_MAP,
        template_path=template_path,
        pre_build=None,
        post_build=mapping.post_build if hasattr(mapping, 'post_build') else None,
    )

    # Debug: Show injected workflow nodes
    print("\n🔧 WORKFLOW NODES (after param injection):")
    injected_node_ids = set(node_id for node_id, _ in mapping.PARAM_MAP.values())
    print(f"  Showing {len(injected_node_ids)} nodes with injected parameters: {sorted(injected_node_ids)}\n")

    for node_id in sorted(injected_node_ids, key=int):
        if node_id in workflow:
            print(f"\n  Node {node_id} - {workflow[node_id].get('class_type', 'Unknown')}:")
            pprint.pprint(workflow[node_id].get('inputs', {}), width=120, indent=4)
    print("\n" + "="*80 + "\n")

    # Execute workflow
    try:
        results = await run_workflow(workflow)
    except WorkflowError as e:
        # Custom workflow errors with user-friendly messages
        raise HTTPException(status_code=400, detail=e.user_message)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail="Service unavailable: Cannot connect to ComfyUI")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail="Request timeout: Workflow took too long")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail="Workflow execution failed")
    except Exception as e:
        # Unexpected errors
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

    # Extract output URLs and metadata
    output_urls = [result["s3_url"] for result in results if "s3_url" in result]
    output_metadata = []
    for result in results:
        metadata = result.get("metadata")
        if metadata:
            print(f"[WAN] Metadata for {result.get('filename')}: {metadata}")
            output_metadata.append(metadata)
        else:
            print(f"[WAN] No metadata for {result.get('filename')}")
            output_metadata.append({})

    # Update generation record
    update_generation_result(DB_PATH, generation_id, output_urls, "completed")

    return WanVaceResponse(
        status="completed",
        output_urls=output_urls,
        output_metadata=output_metadata,
        message=f"Generated {len(results)} output(s)",
        generation_id=generation_id,
    )


################################################################################
#                    COMMON SHARED ROUTES                                      #
################################################################################

@router.get("/list")
async def wan_list():
    """List all available WAN pipelines from registry."""
    pipelines = json.loads(REGISTRY_PATH.read_text())
    return {"pipelines": pipelines}


@router.get("/{slug}/params")
async def get_params(slug: str):
    """Get parameter schema and metadata for a specific workflow."""
    mapping = SLUG_TO_MAPPING.get(slug)
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    # Get schema based on slug
    if slug == "wan2-2-animate-character-swap":
        schema = WanAnimateRequest
    elif slug == "wan2-2-fun-vace-mask-edit-controlnet":
        schema = WanVaceRequest
    else:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    return {"params": inspect_params(schema, mapping.PARAM_META)}

# Specifics of the implementation to be done later.
@router.get("/{slug}/{generation_id}")
async def get_generation(slug: str, generation_id: str):
    """Retrieve a generation request by its ID."""
    if slug not in SLUG_TO_MAPPING:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    generation = get_generation_by_id(DB_PATH, slug, generation_id)
    if not generation:
        raise HTTPException(status_code=404, detail=f"Generation '{generation_id}' not found")

    return generation


@router.post("/{slug}/upload")
async def upload_file(slug: str, request: Request, file: UploadFile):
    """Upload image or video files for WAN workflows."""
    if slug not in SLUG_TO_MAPPING:
        raise HTTPException(status_code=404, detail=f"Pipeline '{slug}' not found")

    # Define allowed file types and size limits
    ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    ALLOWED_VIDEO_TYPES = {"video/mp4"}
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp4"}
    MAX_IMAGE_SIZE = 15 * 1024 * 1024  # 15 MB
    MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB

    # Extract file extension
    # file.filename is a string attribute that provides the original name of the file as it was sent by the client
    if not file.filename:
      raise HTTPException(status_code=400, detail="Filename is required")  
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

    # Generate unique filename
    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"

    print(f"[UPLOAD] Processing file in memory: {unique_name} ({file_size / (1024 * 1024):.2f}MB)")

    # Validate file content matches claimed type using magic bytes (from memory - no disk write)
    try:
        detected_mime = magic.from_buffer(file_content, mime=True)

        # Define allowed MIME types for each extension
        valid_mimes = {
            ".png": ["image/png"],
            ".jpg": ["image/jpeg"],
            ".jpeg": ["image/jpeg"],
            ".webp": ["image/webp"],
            ".mp4": ["video/mp4"]
        }

        expected = valid_mimes.get(ext, [])
        if detected_mime not in expected:
            raise HTTPException(
                status_code=400,
                detail=f"File content doesn't match extension. Expected {expected}, got '{detected_mime}'"
            )

        print(f"[UPLOAD] File type validation passed: {detected_mime}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"File validation failed: {str(e)}"
        )

    # Call model-specific validation if available
    mapping = SLUG_TO_MAPPING[slug]
    if hasattr(mapping, 'validate_upload'):
        # ffprobe/PIL need a file path, so stage bytes to a temp file.
        # NamedTemporaryFile with delete=True auto-cleans on context exit,
        # covering normal returns, exceptions, and asyncio cancellation.
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / "comfyui_upload_validation"
        temp_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(suffix=ext, dir=temp_dir, delete=True) as tmp:
            tmp.write(file_content)
            tmp.flush() # Forces to write everything in the buffer, into the disk
            file_type = "video" if is_video else "image"
            try:
                mapping.validate_upload(Path(tmp.name), file_type)
                print(f"[UPLOAD] {file_type.capitalize()} validation passed")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                print(f"[UPLOAD] Warning: Validation error: {e}")

    # Bail out if the client has already disconnected — avoids an orphaned S3 upload
    if await request.is_disconnected():
        print(f"[UPLOAD] Client disconnected before S3 upload; skipping {unique_name}")
        raise HTTPException(status_code=499, detail="Client disconnected before upload completed")

    # Upload bytes directly to S3 (no disk storage)
    content_type = file.content_type or "application/octet-stream"
    try:
        s3_url = await upload_to_s3(file_content, content_type, filename=unique_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")

    print(f"[UPLOAD] Uploaded to S3 from memory: {unique_name}")

    return {
        "filename": unique_name,
        "preview_url": s3_url
    }
