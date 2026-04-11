# ComfyUI Workflows Backend

Backend service for ComfyUI Workflows App.

## Prerequisites

- Python 3.10 or higher
- FFmpeg (for video processing)
- ComfyUI installed and running
- AWS S3 bucket (optional, for cloud storage)

## Installation

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd <repo-name>/backend
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

### 5. Configure Environment

Create a `.env` file in the backend directory:


### 6. Set Up ComfyUI

Ensure ComfyUI is installed with required models:

```bash
# Required models in ComfyUI/models/
├── checkpoints/
│   └── Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors
├── vae/
│   └── wan_2.1_vae.safetensors
├── text_encoders/
│   └── umt5-xxl-enc-bf16.safetensors
├── clip_vision/
│   └── clip_vision_h.safetensors
└── loras/
    ├── WanAnimate_relight_lora_fp16.safetensors
    └── lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
```

## API Endpoints

### List Pipelines

```bash
GET /wan/list
```

Returns available WanVideo pipelines.

### Upload File

```bash
POST /wan/{slug}/upload
Content-Type: multipart/form-data

{
  "file": <binary>
}
```

Upload reference image or input video. Returns:
- `filename`: Unique filename
- `preview_url`: S3 URL (if configured)

**Validation:**
- Videos: ≤81 frames, must be 4k+1 format (1, 5, 9, 13, ..., 77, 81)
- Images: PNG, JPG, JPEG, WEBP (max 50MB)
- Videos: MP4 (max 500MB)

### Generate Video

```bash
POST /wan/{slug}
Content-Type: application/json

{
  "reference_image": "image.jpg",
  "input_video": "video.mp4",
  "positive_prompt": "A person in casual clothing...",
  "negative_prompt": "low quality, blurry...",
  "mode": "replace",  // or "animate"
  "height": 720,
  "steps": 8,
  "cfg": 1,
  "shift": 8,
  "seed": -1,
  "relight_lora_strength": 0.7,
  "distill_lora_strength": 1.2,
  "pose_strength": 1.0,
  "face_strength": 1.0
}
```

Returns:
- `output_urls`: Array of generated video URLs
- `output_metadata`: Video metadata (width, height, fps, etc.)
- `generation_id`: Unique generation ID

## Project Structure

```
backend/
├── src/
│   ├── main.py                 # FastAPI application entry point
│   ├── routes/
│   │   └── wan.py             # WanVideo API routes
│   ├── schemas/
│   │   └── wan.py             # Pydantic models
│   ├── services/
│   │   ├── mappings/
│   │   │   ├── wan_animate.py # Workflow parameter mapping
│   │   │   └── registry.json  # Pipeline registry
│   │   ├── workflow_builder.py  # Workflow construction
│   │   ├── workflow_runner.py   # ComfyUI execution
│   │   ├── comfyui_client.py    # ComfyUI API client
│   │   └── s3_upload.py         # S3 file upload
│   ├── config/
│   │   └── settings.py        # Configuration management
│   └── utils/
│       ├── utils_video.py     # Video processing utilities
│       └── utils_db.py        # Generation history tracking
├── comfy_workflows/
│   └── wan/                   # ComfyUI workflow templates
├── dummy_db/                  # Local generation history
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Video Requirements

### Frame Count
- **Maximum:** 81 frames
- **Format:** Must be of the form `4k + 1` where k is an integer

## Mode Types

### Replace Mode (Default)
- Swaps character face/appearance
- Preserves original background and lighting
- Uses background mask for clean separation
- Best for: Character replacement, face swaps

**Workflow behavior:**
- Connects `bg_images` and `mask` to Node 62

### Animate Mode
- Full scene transformation
- AI-generated backgrounds
- Complete creative control
- Best for: Artistic transformations, scene changes

**Workflow behavior:**
- Disconnects `bg_images` and `mask` from Node 62

## Troubleshooting

### Video Frame Validation Error

```
Video has 72 frames. Frame count must be of the form 4k+1. Valid counts: 69 or 73.
```

**Solution:**
Trim your video to match a valid frame count using FFmpeg.


### Adding New Pipelines

1. Create workflow JSON in `comfy_workflows/<pipeline_name>/`
2. Create mapping file in `src/services/mappings/<pipeline_name>.py`
3. Add schema in `src/schemas/<pipeline_name>.py`
4. Register in `src/services/mappings/registry.json`
5. Add route in `src/routes/<pipeline_name>.py`
