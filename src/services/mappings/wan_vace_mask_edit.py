import random
import subprocess
from pathlib import Path
from ...config.settings import settings
from ...utils.utils_video import get_video_dimensions, wan_calculate_aspect_ratio_dimensions

NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，"
    "整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，"
    "画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，"
    "静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

WORKFLOW_SUBDIR = "wan"
TEMPLATE = "final_v1.0_benji_Wan_2.2_Fun_VACE_Mask Edit_ControlNet.json"

# { param_name: (node_id, field_name) }
PARAM_MAP = {
    # Inputs
    "reference_image":       ("465", "image"),
    "input_video":           ("460", "video"),

    # Prompts
    "positive_prompt":       ("15",  "text"),
    "negative_prompt":       ("16",  "text"),

    # Resolution
    "width":                 ("19",  "value"),
    "height":                ("20",  "value"),
    "frames":                ("21",  "value"),  # Auto-detected from input video

    # Sampler
    "steps":                 ("449", "value"),
    "shift":                 ("557", "value"),
    "seed":                  ("448", "value"),

    # LoRA strengths - Node 570 (high noise) and Node 569 (low noise)
    "high_noise_lora_strength": ("570", "strength_model"),
    "low_noise_lora_strength":  ("569", "strength_model"),

    # WanVaceToVideo strength parameters
    "vace_strength_high":    ("17",  "strength"),  # First pass (high noise)
    "vace_strength_low":     ("491", "strength"),  # Second pass (low noise)
}


PARAM_META = {
    "reference_image": {
        "label": "Reference Image",
        "group": "Inputs",
        "description": "The face/character image to use in the video",
    },
    "input_video": {
        "label": "Input Video",
        "group": "Inputs",
        "description": "The source video to apply VACE processing to",
    },
    "positive_prompt": {
        "label": "Prompt",
        "group": "Prompts",
        "description": "Describe what the scene should look like",
    },
    "negative_prompt": {
        "label": "Negative Prompt",
        "group": "Prompts",
        "description": "Things to avoid in the output (leave empty for default)",
    },
    "width": {
        "label": "Width",
        "group": "Resolution",
        "description": "Output video width in pixels",
    },
    "height": {
        "label": "Height",
        "group": "Resolution",
        "description": "Output video height in pixels",
    },
    "steps": {
        "label": "Steps",
        "group": "Sampler",
        "description": "How many times the AI refines the video. More = better quality but slower",
    },
    "shift": {
        "label": "Shift",
        "group": "Sampler",
        "description": "Controls the noise schedule. Higher values add more detail",
    },
    "seed": {
        "label": "Seed",
        "group": "Sampler",
        "description": "Set to -1 for random. Use a fixed number to reproduce the same result",
    },
    "high_noise_lora_strength": {
        "label": "High Noise LoRA Strength",
        "group": "LoRA Strengths",
        "description": "Strength of the high noise LoRA for first pass processing",
    },
    "low_noise_lora_strength": {
        "label": "Low Noise LoRA Strength",
        "group": "LoRA Strengths",
        "description": "Strength of the low noise LoRA for second pass refinement",
    },
    "vace_strength_high": {
        "label": "VACE Strength (High Noise)",
        "group": "VACE Settings",
        "description": "Strength of VACE processing in first pass (0.0-1.0)",
    },
    "vace_strength_low": {
        "label": "VACE Strength (Low Noise)",
        "group": "VACE Settings",
        "description": "Strength of VACE processing in second pass (0.0-1.0)",
    },
}



def pre_build(params: dict) -> dict:
    """Pre-process parameters before building the workflow."""
    # Generate random seed if not specified
    if params.get("seed", -1) == -1:
        params["seed"] = random.randint(0, 2**32)

    # Use default negative prompt if not provided
    if not params.get("negative_prompt"):
        params["negative_prompt"] = NEGATIVE_PROMPT

    # Process input video to extract metadata
    input_video = params.get("input_video")
    requested_width = params.get("width")
    requested_height = params.get("height")

    if input_video:
        video_dims = None
        video_frame_count = None
        import subprocess
        import json

        # Determine video source (URL or local file)
        if input_video.startswith("http://") or input_video.startswith("https://"):
            video_source = input_video
        else:
            video_source = str(Path(settings.comfyui_path) / settings.comfyui_input_folder / input_video)

        # Get video metadata: dimensions, frame count, and frame rate
        video_fps = None
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,nb_frames,r_frame_rate",
                "-of", "json",
                video_source
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if data.get("streams") and len(data["streams"]) > 0:
                    stream = data["streams"][0]
                    width = stream.get("width")
                    height = stream.get("height")
                    if width and height:
                        video_dims = (width, height)

                    # Get frame count
                    nb_frames = stream.get("nb_frames")
                    if nb_frames and nb_frames != "N/A":
                        video_frame_count = int(nb_frames)

                    # Get frame rate (format: "24/1")
                    r_frame_rate = stream.get("r_frame_rate")
                    if r_frame_rate:
                        num, denom = map(int, r_frame_rate.split('/'))
                        video_fps = num / denom
        except Exception:
            pass

        # Fallback method for frame count if not available
        if not video_frame_count:
            try:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-count_frames",
                    "-show_entries", "stream=nb_read_frames",
                    "-of", "default=nokey=1:noprint_wrappers=1",
                    video_source
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    video_frame_count = int(result.stdout.strip())
            except Exception:
                pass

        # Validate and set frame count
        if video_frame_count:
            # Validate: frames <= 81
            if video_frame_count > 81:
                raise ValueError(
                    f"Video has {video_frame_count} frames (max: 81). Please trim to 81 frames or less."
                )

            # Validate: frames = 4n + 1 (i.e., 1, 5, 9, 13, ..., 77, 81)
            if (video_frame_count - 1) % 4 != 0:
                n_lower = (video_frame_count - 1) // 4
                n_upper = n_lower + 1
                valid_lower = 4 * n_lower + 1
                valid_upper = 4 * n_upper + 1

                if valid_upper <= 81:
                    suggestion = f"{valid_lower} or {valid_upper}"
                else:
                    suggestion = f"{valid_lower}"

                raise ValueError(
                    f"Video has {video_frame_count} frames. Frame count must be of the form 4k+1. "
                    f"Valid counts: {suggestion}. Please trim your video."
                )

            print(f"[WAN VACE] Video frame validation passed: {video_frame_count} frames")

            # Set frames parameter if not provided or override with detected
            params["frames"] = video_frame_count

        # Set output dimensions: preserve input aspect ratio, scale to requested height
        if video_dims and requested_height:
            original_width, original_height = video_dims
            new_width, new_height = wan_calculate_aspect_ratio_dimensions(
                requested_height, original_width, original_height
            )
            params["width"] = new_width
            params["height"] = new_height
            print(f"[WAN VACE] Dimensions: {original_width}x{original_height} -> {new_width}x{new_height}")

        # Auto-detect and set frame rate
        if video_fps:
            detected_fps = int(round(video_fps))
            print(f"[WAN VACE] Detected frame rate: {detected_fps} fps")
        else:
            print(f"[WAN VACE] Could not detect frame rate from video")

    return params


def validate_upload(file_path: Path, file_type: str) -> None:
    """
    Validate uploaded files for WAN VACE workflow.

    For images, validates:
    - Image is not corrupted (can be decoded)
    - Dimensions <= 1080 (HD resolution limit)

    For videos, validates:
    - Frame count <= 81
    - Frame count must be 4k+1 format (1, 5, 9, 13, ..., 77, 81)

    Raises ValueError if validation fails.
    Called at upload time to fail fast before S3 upload.
    """
    if file_type == "image":
        # Validate image integrity and dimensions
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                # Verify image is not corrupted
                img.verify()

                # Re-open to get dimensions (verify() closes the image)
                with Image.open(file_path) as img2:
                    width, height = img2.size

                    # Validate dimensions (max 1080p for WAN VACE)
                    if width > 1080 or height > 1080:
                        raise ValueError(
                            f"Image dimensions too large: {width}x{height} (max: 1080x1080)"
                        )

                    print(f"[WAN VACE Upload] Image validation passed: {width}x{height} {img2.format}")

        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            raise ValueError(f"Invalid or corrupted image: {str(e)}")
        return

    if file_type != "video":
        # Unknown file type
        return

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

        if result.returncode != 0 or not result.stdout.strip():
            print(f"[WAN VACE Upload] Warning: Could not detect frame count")
            return  # Skip validation if ffprobe fails

        frame_count = int(result.stdout.strip())

        # Validate: frames <= 81
        if frame_count > 81:
            raise ValueError(
                f"Video has {frame_count} frames (max: 81). Please trim to 81 frames or less."
            )

        # Validate: frames = 4n + 1 (i.e., 1, 5, 9, 13, ..., 77, 81)
        if (frame_count - 1) % 4 != 0:
            n_lower = (frame_count - 1) // 4
            n_upper = n_lower + 1
            valid_lower = 4 * n_lower + 1
            valid_upper = 4 * n_upper + 1

            if valid_upper <= 81:
                suggestion = f"{valid_lower} or {valid_upper}"
            else:
                suggestion = f"{valid_lower}"

            raise ValueError(
                f"Video has {frame_count} frames. Frame count must be of the form 4k+1. "
                f"Valid counts: {suggestion}. Please trim your video."
            )

        print(f"[WAN VACE Upload] Video validation passed: {frame_count} frames")

    except subprocess.TimeoutExpired:
        print(f"[WAN VACE Upload] Warning: ffprobe timeout, skipping validation")
    except ValueError:
        # Re-raise validation errors
        raise
    except Exception as e:
        print(f"[WAN VACE Upload] Warning: Could not validate video: {e}")
