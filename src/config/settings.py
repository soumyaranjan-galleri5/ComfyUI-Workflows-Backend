from pathlib import Path

from pydantic_settings import BaseSettings

# Get the backend directory path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "Comfy Workflows"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ComfyUI
    comfyui_server_url: str = "http://127.0.0.1:8188"
    comfyui_path: str = "/home/azureuser/ComfyUI"
    comfyui_input_folder: str = "input"
    comfyui_output_folder: str = "output"
    comfyui_timeout: int = 9999
    workflows_dir: str = str(BACKEND_DIR / "comfy_workflows")

    # S3
    s3_api_key: str = ""
    s3_url_endpoint: str = ""

    # Default test/example assets
    default_reference_image: str = ""
    default_input_video: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
