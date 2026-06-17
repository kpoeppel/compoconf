"""
I/O utilities for compoconf: convenience helpers for loading configuration files.

This is intentionally kept out of the core ``parsing`` module so that ``parsing`` stays focused on
turning already-loaded data structures into typed configs, while file/format concerns live here.
"""

import json
from pathlib import Path
from typing import Optional

from compoconf.parsing import parse_config


def parse_file(
    config_class, path, *, strict: bool = True, strict_types: bool = False, file_format: Optional[str] = None
):
    """
    Load a configuration file and parse it into a typed configuration object.

    A thin convenience wrapper around :func:`compoconf.parse_config` that reads JSON or YAML from
    disk. The format is inferred from the file extension (``.json`` -> JSON; ``.yaml`` / ``.yml`` ->
    YAML) unless ``file_format`` is provided explicitly.

    Args:
        config_class: The target configuration class (typically a dataclass).
        path: Path to the configuration file (``str`` or ``os.PathLike``).
        strict: Forwarded to :func:`compoconf.parse_config`; if True, raise on unknown keys.
        strict_types: Forwarded to :func:`compoconf.parse_config`; if True, disable silent scalar
            coercion.
        file_format: Optional explicit format -- one of ``"json"``, ``"yaml"``, ``"yml"`` --
            overriding extension-based detection.

    Returns:
        An instance of ``config_class`` parsed from the file contents.

    Raises:
        ValueError: If the file format cannot be determined or is unsupported.
        ImportError: If YAML parsing is requested but PyYAML is not installed.

    Example:
        config = parse_file(ModelConfig, "config.yaml")
    """
    path = Path(path)
    fmt = (file_format or path.suffix.lstrip(".")).lower()
    if fmt == "json":
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    elif fmt in ("yaml", "yml"):
        try:
            import yaml  # type: ignore  # pylint: disable=import-outside-toplevel,import-error
        except ImportError as exc:
            raise ImportError(
                "Parsing YAML config files requires PyYAML. Install it with `pip install pyyaml` "
                "(or `pip install compoconf[omegaconf]`), or pass a JSON file instead."
            ) from exc
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    else:
        raise ValueError(
            f"Cannot determine config file format for '{path}' (extension/format '{fmt}'). "
            "Use a .json/.yaml/.yml file or pass file_format=..."
        )
    return parse_config(config_class, data, strict=strict, strict_types=strict_types)
