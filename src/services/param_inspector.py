from typing import Any, get_args, get_origin, Union

from pydantic import BaseModel


def inspect_params(model: type[BaseModel], meta: dict[str, dict]) -> list[dict[str, Any]]:
    """Build param definitions by combining Pydantic field info with human-written metadata.

    Auto-detects: type, default, min, max from the Pydantic model.
    Meta provides: label, description, group per field name.
    """
    params = []

    for name, field_info in model.model_fields.items():
        entry = meta.get(name)
        if not entry:
            continue

        # Resolve the base annotation (unwrap Optional)
        annotation = field_info.annotation
        origin = get_origin(annotation)
        if origin is Union:
            args = [a for a in get_args(annotation) if a is not type(None)]
            annotation = args[0] if args else str

        # Auto-detect field type
        if "image" in name:
            field_type = "file:image"
        elif "video" in name:
            field_type = "file:video"
        elif "prompt" in name:
            field_type = "textarea"
        elif annotation is float:
            field_type = "float"
        elif annotation is int:
            field_type = "int"
        else:
            field_type = "text"

        # Build param def
        param: dict[str, Any] = {
            "name": name,
            "label": entry.get("label", name.replace("_", " ").title()),
            "type": field_type,
            "group": entry.get("group", "General"),
            "description": entry.get("description", ""),
        }

        # Default
        if field_info.default is not None:
            param["default"] = field_info.default

        # Min/max from Pydantic metadata
        if field_info.metadata:
            for constraint in field_info.metadata:
                if hasattr(constraint, "ge"):
                    param["min"] = constraint.ge
                if hasattr(constraint, "le"):
                    param["max"] = constraint.le

        # Step
        if field_type == "float":
            param["step"] = 0.1
        elif field_type == "int":
            param["step"] = 1

        params.append(param)

    return params
