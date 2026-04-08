"""Video processing utility functions."""
import json
import subprocess
from pathlib import Path
from typing import Optional


def get_video_metadata(video_path: Path) -> Optional[dict[str, any]]:
    """Get video metadata from input file using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        Dictionary with keys: width, height, duration, frame_count, fps, codec_name
        or None if detection fails
    """
    try:
        if not video_path.exists():
            return None

        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,codec_name,r_frame_rate,nb_frames",
            "-of", "json",
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if data.get("streams") and len(data["streams"]) > 0:
                stream = data["streams"][0]

                # Parse frame rate (format: "24/1")
                fps = None
                r_frame_rate = stream.get("r_frame_rate")
                if r_frame_rate:
                    num, denom = map(int, r_frame_rate.split('/'))
                    fps = round(num / denom, 2) if denom != 0 else None

                # Get frame count
                nb_frames = stream.get("nb_frames")
                frame_count = int(nb_frames) if nb_frames and nb_frames != "N/A" else None

                # If frame count not available, try alternative method
                if not frame_count:
                    try:
                        cmd_frames = [
                            "ffprobe", "-v", "error",
                            "-select_streams", "v:0",
                            "-count_frames",
                            "-show_entries", "stream=nb_read_frames",
                            "-of", "default=nokey=1:noprint_wrappers=1",
                            str(video_path)
                        ]
                        result_frames = subprocess.run(cmd_frames, capture_output=True, text=True, timeout=10)
                        if result_frames.returncode == 0 and result_frames.stdout.strip():
                            frame_count = int(result_frames.stdout.strip())
                    except Exception:
                        pass

                # If still no frame count, calculate from duration and fps
                if not frame_count and fps and stream.get("duration"):
                    frame_count = int(float(stream.get("duration")) * fps)

                return {
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "duration": float(stream.get("duration", 0)),
                    "frame_count": frame_count,
                    "fps": fps,
                    "codec_name": stream.get("codec_name"),
                }
    except Exception:
        pass

    return None


def get_video_dimensions(video_path: Path) -> Optional[tuple[int, int]]:
    """Get video dimensions from input file using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        Tuple of (width, height) or None if detection fails
    """
    try:
        if not video_path.exists():
            return None

        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            width, height = map(int, result.stdout.strip().split('x'))
            return width, height
    except Exception:
        pass

    return None


def calculate_aspect_ratio_dimensions(
    target_height: int,
    original_width: int,
    original_height: int
) -> tuple[int, int]:
    """Calculate width that maintains aspect ratio for given target height.

    Args:
        target_height: Desired output height
        original_width: Original video width
        original_height: Original video height

    Returns:
        Tuple of (new_width, target_height) with width rounded to multiple of 8
    """
    aspect_ratio = original_width / original_height
    new_width = int(target_height * aspect_ratio)

    # Round to nearest multiple of 8 (important for video encoding)
    new_width = (new_width + 4) // 8 * 8

    return new_width, target_height
