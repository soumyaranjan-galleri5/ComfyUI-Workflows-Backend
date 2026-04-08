import random
from pathlib import Path
from ...config.settings import settings
from ...utils.utils_video import get_video_dimensions, calculate_aspect_ratio_dimensions

NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，"
    "整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，"
    "画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，"
    "静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

TEMPLATE = "wan/final_v1.0_Workflow_ComfyUI_Wan_2.2_Animate_Swap_Characters_and_Lip-Sync.json"

# { param_name: (node_id, field_name) }
PARAM_MAP = {
    # Inputs
    "reference_image":       ("57",  "image"),
    "input_video":           ("63",  "video"),

    # Prompts
    "positive_prompt":       ("65",  "positive_prompt"),
    "negative_prompt":       ("65",  "negative_prompt"),

    # Resolution
    "width":                 ("150", "value"),
    "height":                ("151", "value"),

    # Sampler
    "steps":                 ("27",  "steps"),
    "cfg":                   ("27",  "cfg"),
    "shift":                 ("27",  "shift"),
    "seed":                  ("27",  "seed"),

    # LoRA strengths
    "relight_lora_strength": ("171", "strength_0"),
    "distill_lora_strength": ("171", "strength_1"),

    # Animate embeds
    "pose_strength":         ("62",  "pose_strength"),
    "face_strength":         ("62",  "face_strength"),

    # Context
    "context_frames":        ("110", "context_frames"),
    "context_overlap":       ("110", "context_overlap"),

    # Output - Node 30 (Video 2)
    "output_frame_rate":     ("30",  "frame_rate"),
    "output_crf":            ("30",  "crf"),

    # Output - Node 75 (Video 1 intermediate) - not saved, but keep for consistency
    "output_frame_rate_video1": ("75",  "frame_rate"),
    "output_crf_video1":        ("75",  "crf"),

    # Output - Node 186 (ACTUAL Video 1 output with audio) - this is the real output!
    "output_frame_rate_video1_actual": ("186",  "frame_rate"),
    "output_crf_video1_actual":        ("186",  "crf"),

    # Preprocessing visualization nodes - must match input video frame rate
    "preprocess_frame_rate_vitpose":  ("174", "frame_rate"),  # Pose/Face detection viz
    "preprocess_frame_rate_posedraw": ("181", "frame_rate"),  # Pose skeleton draw
}


PARAM_META = {
    "reference_image": {
        "label": "Reference Image",
        "group": "Inputs",
        "description": "The face/character image to swap into the video",
    },
    "input_video": {
        "label": "Input Video",
        "group": "Inputs",
        "description": "The source video whose character will be replaced",
    },
    "positive_prompt": {
        "label": "Prompt",
        "group": "Inputs",
        "description": "Describe what the scene should look like",
    },
    "negative_prompt": {
        "label": "Negative Prompt",
        "group": "Inputs",
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
    "cfg": {
        "label": "CFG",
        "group": "Sampler",
        "description": "How closely the AI follows your prompt. Higher = more literal",
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
    "relight_lora_strength": {
        "label": "Relight LoRA",
        "group": "LoRA Strengths",
        "description": "Controls lighting consistency. Lower = subtler, higher = stronger effect",
    },
    "distill_lora_strength": {
        "label": "Distill LoRA",
        "group": "LoRA Strengths",
        "description": "Speed optimization strength. Higher = faster but may reduce quality",
    },
    "pose_strength": {
        "label": "Pose Strength",
        "group": "Animate Embeds",
        "description": "How strongly the body pose is transferred from the source video",
    },
    "face_strength": {
        "label": "Face Strength",
        "group": "Animate Embeds",
        "description": "How strongly the face is swapped from the reference image",
    },
    "context_frames": {
        "label": "Context Frames",
        "group": "Context",
        "description": "Number of frames the AI processes at once. More = smoother but uses more memory",
    },
    "context_overlap": {
        "label": "Context Overlap",
        "group": "Context",
        "description": "Overlap between frame batches. Higher = smoother transitions between batches",
    },
    "output_frame_rate": {
        "label": "Frame Rate",
        "group": "Output",
        "description": "Frames per second of the output video",
    },
    "output_crf": {
        "label": "CRF",
        "group": "Output",
        "description": "Video compression quality. Lower = better quality, larger file",
    },
}


def pre_build(params: dict) -> dict:
    if params.get("seed", -1) == -1:
        params["seed"] = random.randint(0, 2**53)

    if not params.get("negative_prompt"):
        params["negative_prompt"] = NEGATIVE_PROMPT

    # Preserve aspect ratio and adjust context_frames based on input video
    input_video = params.get("input_video")
    requested_width = params.get("width")
    requested_height = params.get("height")

    if input_video:
        video_dims = None
        video_frame_count = None
        import subprocess

        # Check if input_video is a URL
        if input_video.startswith("http://") or input_video.startswith("https://"):
            # For URLs, use ffprobe directly on the URL
            video_source = input_video
        else:
            # For uploaded filenames, check in ComfyUI input folder
            video_source = str(Path(settings.comfyui_path) / settings.comfyui_input_folder / input_video)

        # Get video dimensions, frame count, and frame rate
        video_fps = None
        try:
            # Get dimensions and frame rate
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,nb_frames,r_frame_rate",
                "-of", "json",
                video_source
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                import json
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

        # If nb_frames wasn't available, try alternative method
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

        # Update dimensions to maintain aspect ratio
        if video_dims and requested_width and requested_height:
            original_width, original_height = video_dims

            # Calculate new dimensions maintaining aspect ratio based on requested height
            new_width, new_height = calculate_aspect_ratio_dimensions(
                requested_height, original_width, original_height
            )

            # Update params with aspect-ratio-corrected dimensions
            params["width"] = new_width
            params["height"] = new_height

        # Adjust context_frames if it exceeds video frame count
        if video_frame_count:
            context_frames = params.get("context_frames", 20)
            if context_frames > video_frame_count:
                # Set context_frames to video_frame_count or slightly less
                params["context_frames"] = video_frame_count
                # Also adjust context_overlap if needed
                context_overlap = params.get("context_overlap", 10)
                if context_overlap >= video_frame_count // 2:
                    params["context_overlap"] = max(0, video_frame_count // 4)

        # Use input video's frame rate to preserve all frames (unless user wants custom)
        use_custom_frame_rate = params.get("use_custom_frame_rate", False)
        print(f"[WAN] Auto-detection: use_custom={use_custom_frame_rate}, video_fps={video_fps}, video_frames={video_frame_count}")
        if video_fps and not use_custom_frame_rate:
            # Auto-detect: Override output_frame_rate with input fps to ensure no frame loss
            detected_fps = int(round(video_fps))
            print(f"[WAN] Setting frame rate to detected: {detected_fps} fps")
            params["output_frame_rate"] = detected_fps
            # Set frame rate for BOTH Video 1 nodes (75 and 186)
            params["output_frame_rate_video1"] = detected_fps
            params["output_frame_rate_video1_actual"] = detected_fps
            # Set frame rate for preprocessing visualization nodes (174, 181)
            params["preprocess_frame_rate_vitpose"] = detected_fps
            params["preprocess_frame_rate_posedraw"] = detected_fps
        else:
            # When using custom frame rate, both videos should use the same custom rate
            if "output_frame_rate" in params:
                print(f"[WAN] Using custom frame rate: {params['output_frame_rate']} fps")
                params["output_frame_rate_video1"] = params["output_frame_rate"]
                params["output_frame_rate_video1_actual"] = params["output_frame_rate"]
                # Set custom frame rate for preprocessing nodes too
                params["preprocess_frame_rate_vitpose"] = params["output_frame_rate"]
                params["preprocess_frame_rate_posedraw"] = params["output_frame_rate"]

        # Sync CRF for Video 1 with Video 2 (both nodes)
        if "output_crf" in params:
            params["output_crf_video1"] = params["output_crf"]
            params["output_crf_video1_actual"] = params["output_crf"]

    return params
