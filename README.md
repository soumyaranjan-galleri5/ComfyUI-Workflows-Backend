# ComfyUI Workflows Backend

Backend service for ComfyUI workflows via REST API.

## Overview

FastAPI-based backend that provides REST API endpoints for ComfyUI workflow execution. The service handles:

- Input validation and preprocessing
- Workflow parameter mapping to ComfyUI nodes
- Workflow execution management
- Output retrieval and S3 upload

**Note:** A separate service running the ComfyUI API is required for workflow execution.

### Architecture

```
API Request → Input Validation → Parameter Mapping → Workflow Builder
    → ComfyUI Execution → Output Processing → S3 Upload → Response
```

### Key Components

- **Routes**: API endpoint definitions
- **Schemas**: Pydantic models for request/response validation
- **Services**: Core logic
  - `workflow_builder.py`: Constructs ComfyUI workflow JSON
  - `workflow_runner.py`: Manages execution lifecycle
  - `comfyui_client.py`: ComfyUI API communication
  - `s3_upload.py`: Async S3 upload with disconnect detection
  - `mappings/`: Parameter translation for each workflow
- **Utils**: Helper functions for video processing and database operations

## API Endpoints

**Note:** All endpoints are prefixed with a model-specific route (e.g., `/wan` for WAN models). Replace `{model}` with your model prefix.

### List Workflows

```bash
GET /{model}/list
```

Returns available workflows with metadata.

**Response:**
```json
{
  "pipelines": [
    {
      "slug": "workflow-slug",
      "name": "Workflow Name",
      "description": "...",
      "parameters": {...}
    }
  ]
}
```

### Upload File

```bash
POST /{model}/{slug}/upload
Content-Type: multipart/form-data

{
  "file": <binary>
}
```

Upload reference images or input videos for workflow execution.

**Response:**
```json
{
  "filename": "unique_filename.mp4",
  "preview_url": "https://s3.../file.mp4"
}
```

**Validation:**
- Images: PNG, JPG, JPEG, WEBP (max 15MB)
- Videos: MP4 (max 50MB)
- MIME type verification
- Corruption detection

### Execute Workflow

```bash
POST /{model}/{slug}
Content-Type: application/json

{
  // Workflow-specific parameters
}
```

Execute a ComfyUI workflow with provided parameters.

**Response:**
```json
{
  "generation_id": "uuid",
  "output_urls": ["https://s3.../output.mp4"],
  "output_metadata": {
    "width": 832,
    "height": 720,
    "fps": 30,
    "frames": 53,
    "duration_seconds": 2.5
  }
}
```

### Get Generation (To be implemented)

```bash
GET /{model}/generation/{generation_id}
```

Retrieve generation status and results by ID.

## Set Up Instructions

### Prerequisites

- Python 3.10 or higher
- FFmpeg (for video processing)
- ComfyUI installed and running
- AWS S3 bucket (for output storage)

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

### 4. Run Backend Server

```bash
uvicorn src.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

### 5. Verify Installation

```bash
# Check API health
curl http://localhost:8000/health

# List available workflows (replace {model} with your model prefix)
curl http://localhost:8000/{model}/list
```

## Project Structure

```
backend/
├── src/
│   ├── main.py
│   ├── exceptions.py
│   ├── config/
│   │   └── settings.py
│   ├── routes/
│   │   └── wan.py
│   ├── schemas/
│   │   └── wan.py
│   ├── services/
│   │   ├── comfyui_client.py
│   │   ├── s3_upload.py
│   │   ├── workflow_builder.py
│   │   ├── workflow_runner.py
│   │   ├── param_inspector.py
│   │   └── mappings/
│   │       ├── registry.json
│   │       ├── wan_animate.py
│   │       └── wan_vace_mask_edit.py
│   └── utils/
│       ├── utils_video.py
│       └── utils_db.py
├── comfy_workflows/
│   └── wan/
├── dummy_db/
│   └── wan_generations.json
├── requirements.txt
└── README.md
```

## Adding New Pipelines

### Step 1: Create the Workflow JSON

1. Design your workflow in ComfyUI
2. Export the workflow as JSON (via "Save (API Format)")
3. Save it in the appropriate directory:

```bash
mkdir -p comfy_workflows/wan/my_new_workflow
# Save your workflow.json here
```

### Step 2: Create a Mapping File

Create `src/services/mappings/my_new_workflow.py`:

```python
from typing import Any

# Map API parameters to ComfyUI node inputs
PARAM_MAP = {
    "api_param_name": ("node_id", "input_name"),
    # Example:
    # "positive_prompt": ("6", "text"),
    # "steps": ("10", "steps"),
}

# Define parameter metadata
PARAM_META = {
    "api_param_name": {
        "type": "string",  # or "integer", "float", "boolean"
        "default": "default_value",
        "required": True,
        "description": "Parameter description"
    }
}

def pre_build(params: dict[str, Any]) -> dict[str, Any]:
    """
    Optional: Transform parameters before building workflow.

    Use this for:
    - Validation
    - Computing derived values
    - Preprocessing inputs
    """
    return params

def post_build(workflow: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """
    Optional: Modify workflow JSON after parameter mapping.

    Use this for:
    - Conditional node connections
    - Dynamic workflow structure
    - Complex transformations
    """
    return workflow
```

### Step 3: Register in Registry

Add entry to `src/services/mappings/registry.json`:

```json
{
  "slug": "my-workflow-slug",
  "pipeline": "My Workflow Name - Brief Description",
  "capabilities": [
    "capability-1",
    "capability-2"
  ]
}
```

### Step 4: Create Pydantic Schemas

Add to `src/schemas/{model}.py` (e.g., `src/schemas/wan.py` for WAN models):

```python
from pydantic import BaseModel, Field

class MyWorkflowRequest(BaseModel):
    """Request schema for my workflow."""
    api_param_name: str = Field(..., description="Parameter description")
    # Add all required and optional parameters

class MyWorkflowResponse(BaseModel):
    """Response schema for my workflow."""
    generation_id: str
    output_urls: list[str]
    output_metadata: dict
```

### Step 5: Add API Route

In `src/routes/{model}.py` (e.g., `src/routes/wan.py` for WAN models):

1. Import your mapping and schemas:
```python
from src.services.mappings import my_new_workflow
from src.schemas.wan import MyWorkflowRequest, MyWorkflowResponse
```

2. Add to `SLUG_TO_MAPPING`:
```python
SLUG_TO_MAPPING = {
    # ... existing mappings
    "my-workflow-slug": my_new_workflow,
}
```

3. Create the endpoint:
```python
@router.post("/my-workflow-slug", response_model=MyWorkflowResponse)
async def generate_my_workflow(request: MyWorkflowRequest):
    """Execute my custom workflow."""
    slug = "my-workflow-slug"
    mapping = my_new_workflow
    params = request.model_dump()

    generation_id = str(uuid.uuid4())
    log_generation_request(DB_PATH, generation_id, slug, params)

    try:
        workflow_json = workflow_builder.build(
            registry_path=REGISTRY_PATH,
            slug=slug,
            params=params,
            mapping=mapping
        )

        output_files = await run_workflow(workflow_json)

        output_urls = []
        for file_path in output_files:
            url = await upload_to_s3(file_path, generation_id)
            output_urls.append(url)

        metadata = {
            "width": 0,  # Extract from video
            "height": 0,
            "frames": 0,
            "fps": 0
        }

        update_generation_result(DB_PATH, generation_id, output_urls, metadata)

        return MyWorkflowResponse(
            generation_id=generation_id,
            output_urls=output_urls,
            output_metadata=metadata
        )

    except WorkflowError as e:
        raise HTTPException(status_code=500, detail=str(e))
```
