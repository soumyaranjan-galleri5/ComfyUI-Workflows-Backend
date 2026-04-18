import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from src.config import settings


class ComfyClient:
    """Async client for the ComfyUI REST API."""

    def __init__(self):
        self.server_url = settings.comfyui_server_url.rstrip("/")
        self.timeout = settings.comfyui_timeout
        self.client_id = str(uuid.uuid4())

    def _url(self, path: str) -> str:
        return f"{self.server_url}/{path.lstrip('/')}"

    async def check_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self._url("/system_stats"))
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def upload_file(
        self, file_path: str, subfolder: str = "", overwrite: bool = True
    ) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        files = {"image": (path.name, open(path, "rb"), "application/octet-stream")}
        data = {"overwrite": str(overwrite).lower()}
        if subfolder:
            data["subfolder"] = subfolder

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self._url("/upload/image"), files=files, data=data
            )
        response.raise_for_status()
        result = response.json()

        filename = result.get("name", path.name)
        return filename

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self._url("/prompt"), json=payload)
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            raise RuntimeError(f"ComfyUI queue error: {result['error']}")

        prompt_id = result["prompt_id"]
        return prompt_id

    async def get_history(self, prompt_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self._url(f"/history/{prompt_id}"))
        response.raise_for_status()
        data = response.json()
        return data.get(prompt_id)

    async def wait_for_completion(
        self, prompt_id: str, poll_interval: float = 2.0
    ) -> dict:
        start = time.time()

        while True:
            elapsed = time.time() - start
            if elapsed > self.timeout:
                raise TimeoutError(
                    f"Prompt {prompt_id} timed out after {self.timeout}s"
                )

            history = await self.get_history(prompt_id)
            if history is not None:
                status = history.get("status", {})
                if status.get("status_str") == "error":
                    msg = json.dumps(status, indent=2, ensure_ascii=False)
                    raise RuntimeError(f"Execution failed:\n{msg}")
                return history

            await asyncio.sleep(poll_interval)

    async def download_output_file(
        self, filename: str, subfolder: str = "", file_type: str = "output"
    ) -> bytes:
        base = Path(settings.comfyui_path)
        candidates = [
            base / settings.comfyui_output_folder / subfolder / filename,
            base / settings.comfyui_output_folder / filename,
            base / "video" / subfolder / filename,
            base / "video" / filename,
        ]
        for local_path in candidates:
            if local_path.exists():
                return local_path.read_bytes()

        params = {"filename": filename, "type": file_type, "subfolder": subfolder}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self._url("/view"), params=params)
        response.raise_for_status()
        return response.content

    def get_outputs(self, history: dict) -> dict[str, list[dict]]:
        outputs: dict[str, list[dict]] = {}
        for node_id, node_out in history.get("outputs", {}).items():
            files = []
            for key in ("images", "videos", "gifs"):
                for item in node_out.get(key, []):
                    if item.get("type") != "temp":
                        media = "image" if key == "images" else "video"
                        files.append({**item, "media_type": media})
            if files:
                outputs[node_id] = files
        return outputs
