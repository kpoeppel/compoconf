"""
Tests for :mod:`compoconf.io_utils` -- the ``parse_file`` config-file loader.

Covers every branch of ``parse_file``: JSON loading, YAML loading, the missing-PyYAML error
path, explicit format override, unknown/unsupported formats, ``str`` vs ``Path`` inputs, and
forwarding of ``strict`` / ``strict_types`` to :func:`compoconf.parse_config`.
"""

import json
import sys
from dataclasses import dataclass, field

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface
from compoconf.io_utils import parse_file


@dataclass
class Cfg(ConfigInterface):
    """Config with mixed scalar and collection fields."""

    n: int = 0
    name: str = "x"
    tags: list[int] = field(default_factory=list)


def test_parse_file_json(tmp_path):
    """A ``.json`` file is loaded and parsed into the typed config."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n": 3, "name": "j", "tags": [1, 2]}))
    cfg = parse_file(Cfg, path)
    assert cfg.n == 3
    assert cfg.name == "j"
    assert cfg.tags == [1, 2]


def test_parse_file_accepts_str_path(tmp_path):
    """A string path works as well as a ``Path``."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n": 1}))
    assert parse_file(Cfg, str(path)).n == 1


@pytest.mark.parametrize("suffix", ["yaml", "yml"])
def test_parse_file_yaml(tmp_path, suffix):
    """Both ``.yaml`` and ``.yml`` files are loaded via PyYAML."""
    pytest.importorskip("yaml")
    path = tmp_path / f"config.{suffix}"
    path.write_text("n: 7\nname: y\ntags: [1, 2, 3]\n")
    cfg = parse_file(Cfg, path)
    assert cfg.n == 7
    assert cfg.name == "y"
    assert cfg.tags == [1, 2, 3]


def test_parse_file_yaml_without_pyyaml_raises(tmp_path, monkeypatch):
    """If PyYAML is unavailable, a YAML file yields an actionable ``ImportError``."""
    path = tmp_path / "config.yaml"
    path.write_text("n: 1\n")
    # Make ``import yaml`` fail regardless of whether PyYAML is installed.
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(ImportError, match="PyYAML"):
        parse_file(Cfg, path)


def test_parse_file_explicit_format_override(tmp_path):
    """``file_format`` overrides extension-based detection."""
    path = tmp_path / "config.cfg"  # non-standard extension
    path.write_text(json.dumps({"n": 9}))
    assert parse_file(Cfg, path, file_format="json").n == 9


def test_parse_file_explicit_format_is_case_insensitive(tmp_path):
    """An upper-cased explicit format is normalised."""
    path = tmp_path / "config.data"
    path.write_text(json.dumps({"n": 4}))
    assert parse_file(Cfg, path, file_format="JSON").n == 4


def test_parse_file_unknown_format_raises(tmp_path):
    """An unrecognised extension with no explicit format raises ``ValueError``."""
    path = tmp_path / "config.txt"
    path.write_text("n: 1")
    with pytest.raises(ValueError, match="Cannot determine config file format"):
        parse_file(Cfg, path)


def test_parse_file_forwards_strict_types(tmp_path):
    """``parse_file`` forwards ``strict_types`` to ``parse_config``."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n": "5"}))  # string for an int field
    assert parse_file(Cfg, path).n == 5  # lenient by default
    with pytest.raises(ValueError):
        parse_file(Cfg, path, strict_types=True)


def test_parse_file_forwards_strict(tmp_path):
    """``parse_file`` forwards ``strict`` (unknown-key checking) to ``parse_config``."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n": 1, "unknown_key": 123}))
    with pytest.raises(ValueError):
        parse_file(Cfg, path, strict=True)
    # strict=False tolerates the unknown key
    assert parse_file(Cfg, path, strict=False).n == 1
