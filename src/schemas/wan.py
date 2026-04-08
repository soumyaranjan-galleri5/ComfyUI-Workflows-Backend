from pydantic import BaseModel, Field



class WanAnimateRequest(BaseModel):
    # Inputs
    reference_image: str
    input_video: str
    positive_prompt: str
    negative_prompt: str | None = None

    # Resolution
    width: int = 1080
    height: int = 480

    # Sampler
    steps: int = Field(default=8, ge=1, le=50)
    cfg: float = Field(default=1, ge=0, le=20)
    shift: float = Field(default=8, ge=0, le=20)
    seed: int = Field(default=-1, description="-1 for random seed")

    # LoRA strengths
    relight_lora_strength: float = Field(default=0.7, ge=0, le=2)
    distill_lora_strength: float = Field(default=1.2, ge=0, le=2)

    # Animate embeds
    pose_strength: float = Field(default=1.0, ge=0, le=2)
    face_strength: float = Field(default=1.0, ge=0, le=2)

    # Context
    context_frames: int = Field(default=81, ge=1)
    context_overlap: int = Field(default=32, ge=0)

    # Output
    output_frame_rate: int = Field(default=16, ge=1, le=60)
    use_custom_frame_rate: bool = Field(default=False, description="If False, auto-detect from input video")
    output_crf: int = Field(default=19, ge=0, le=51)


class VideoMetadata(BaseModel):
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    frame_count: int | None = None
    fps: float | None = None
    codec_name: str | None = None


class WanAnimateResponse(BaseModel):
    status: str
    output_urls: list[str] = []
    output_metadata: list[VideoMetadata] = []  # Metadata for each output video
    message: str | None = None
    generation_id: str | None = None
