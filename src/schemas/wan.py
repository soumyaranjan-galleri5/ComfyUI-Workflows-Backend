from pydantic import BaseModel, Field



class WanAnimateRequest(BaseModel):
    # Inputs
    reference_image: str
    input_video: str
    positive_prompt: str
    negative_prompt: str | None = None
    mode: str = Field(default="replace", pattern="^(replace|animate)$", description="replace or animate mode")

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


class WanVaceRequest(BaseModel):
    # Inputs
    reference_image: str
    input_video: str
    positive_prompt: str
    negative_prompt: str | None = None

    # Resolution
    width: int = 832
    height: int = 480

    # Sampler
    steps: int = Field(default=8, ge=1, le=50)
    shift: float = Field(default=8, ge=0, le=20)
    seed: int = Field(default=-1, description="-1 for random seed")

    # LoRA strengths
    high_noise_lora_strength: float = Field(default=0.6, ge=0, le=2)
    low_noise_lora_strength: float = Field(default=1.0, ge=0, le=2)

    # VACE strengths
    vace_strength_high: float = Field(default=0.55, ge=0, le=1)
    vace_strength_low: float = Field(default=0.55, ge=0, le=1)


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


class WanVaceResponse(BaseModel):
    status: str
    output_urls: list[str] = []
    output_metadata: list[VideoMetadata] = []  # Metadata for each output video
    message: str | None = None
    generation_id: str | None = None
