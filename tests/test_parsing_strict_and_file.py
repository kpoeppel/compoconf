"""
Tests for ``strict_types`` (opt-in strict scalar parsing) and the ``parse_file`` helper.
"""

import json
from dataclasses import dataclass, field

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface
from compoconf.io_utils import parse_file
from compoconf.parsing import parse_config


@dataclass
class Cfg(ConfigInterface):
    """Config with mixed scalar and collection fields."""

    n: int = 0
    ratio: float = 0.0
    name: str = "x"
    tags: list[int] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# strict_types                                                                 #
# --------------------------------------------------------------------------- #
def test_lenient_coercion_is_the_default():
    """By default scalars are coerced (this is the existing, documented behavior)."""
    assert parse_config(int, "5") == 5
    assert parse_config(int, 5.9) == 5  # silent truncation, intentionally allowed by default
    assert parse_config(str, 5) == "5"


def test_strict_types_accepts_matching_scalars():
    """With ``strict_types`` matching scalars pass through; int -> float widening is allowed."""
    assert parse_config(int, 5, strict_types=True) == 5
    assert parse_config(str, "a", strict_types=True) == "a"
    widened = parse_config(float, 5, strict_types=True)
    assert widened == 5.0 and isinstance(widened, float)
    assert parse_config(float, 1.5, strict_types=True) == 1.5


@pytest.mark.parametrize(
    "target, value",
    [
        (int, "5"),  # string for int
        (int, 5.9),  # float for int (would truncate)
        (str, 5),  # int for str
        (float, "1.5"),  # string for float
    ],
)
def test_strict_types_rejects_mismatched_scalars(target, value):
    """Mismatched scalar types raise instead of silently coercing."""
    with pytest.raises(ValueError):
        parse_config(target, value, strict_types=True)


def test_strict_types_rejects_bool_for_numeric():
    """``bool`` is not accepted for ``int``/``float`` even though it subclasses ``int``."""
    with pytest.raises(ValueError):
        parse_config(int, True, strict_types=True)
    with pytest.raises(ValueError):
        parse_config(float, False, strict_types=True)


def test_strict_types_propagates_into_nested_fields():
    """``strict_types`` reaches nested dataclass fields."""
    assert parse_config(Cfg, {"n": 1, "ratio": 2.0, "name": "a"}, strict_types=True).n == 1
    with pytest.raises(ValueError):
        parse_config(Cfg, {"n": "1"}, strict_types=True)


def test_strict_types_propagates_into_collections():
    """``strict_types`` reaches elements inside collection fields."""
    assert parse_config(list[int], [1, 2, 3], strict_types=True) == [1, 2, 3]
    with pytest.raises(ValueError):
        parse_config(list[int], ["1", 2], strict_types=True)


# --------------------------------------------------------------------------- #
# parse_file                                                                   #
# --------------------------------------------------------------------------- #
def test_parse_file_json(tmp_path):
    """A JSON file parses into the typed config."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n": 3, "name": "j", "tags": [1, 2]}))
    cfg = parse_file(Cfg, path)
    assert cfg.n == 3
    assert cfg.name == "j"
    assert cfg.tags == [1, 2]


def test_parse_file_yaml(tmp_path):
    """A YAML file parses into the typed config (requires PyYAML)."""
    pytest.importorskip("yaml")
    path = tmp_path / "config.yaml"
    path.write_text("n: 7\nname: y\ntags: [1, 2, 3]\n")
    cfg = parse_file(Cfg, path)
    assert cfg.n == 7
    assert cfg.name == "y"
    assert cfg.tags == [1, 2, 3]


def test_parse_file_forwards_strict_types(tmp_path):
    """``parse_file`` forwards ``strict_types`` to ``parse_config``."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n": "5"}))  # string for an int field
    assert parse_file(Cfg, path).n == 5  # lenient by default
    with pytest.raises(ValueError):
        parse_file(Cfg, path, strict_types=True)


def test_parse_file_explicit_format_override(tmp_path):
    """``file_format`` overrides extension-based detection."""
    path = tmp_path / "config.cfg"  # non-standard extension
    path.write_text(json.dumps({"n": 9}))
    assert parse_file(Cfg, path, file_format="json").n == 9


def test_parse_file_unknown_format_raises(tmp_path):
    """An unrecognised extension with no explicit format raises ``ValueError``."""
    path = tmp_path / "config.txt"
    path.write_text("n: 1")
    with pytest.raises(ValueError):
        parse_file(Cfg, path)
