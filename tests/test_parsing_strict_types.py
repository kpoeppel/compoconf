"""
Tests for ``strict_types`` -- opt-in strict scalar parsing in ``parse_config``.

(``parse_file`` is covered separately in ``test_io_utils.py``.)
"""

from dataclasses import dataclass, field

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface
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
