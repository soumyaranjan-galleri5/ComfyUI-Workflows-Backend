import json
from collections.abc import Callable
from pathlib import Path

from src.config import settings


def build(
    params: dict,
    param_map: dict[str, tuple[str, str]],
    template_path: str,
    pre_build: Callable[[dict], dict] | None = None,
    post_build: Callable[[dict, dict], dict] | None = None,
) -> dict:
    """Build a ComfyUI workflow by injecting params into a JSON template.

    Only fields present in param_map are written. Everything else in the
    template stays untouched.
    """
    path = Path(settings.workflows_dir) / template_path
    workflow = json.loads(path.read_text())

    if pre_build:
        params = pre_build(params)

    for param_name, (node_id, field) in param_map.items():
        if param_name in params:
            workflow[node_id]["inputs"][field] = params[param_name]

    if post_build:
        workflow = post_build(workflow, params)

    return workflow
