"""
Tests for CompoConf
"""

from dataclasses import MISSING, dataclass, field
from typing import Any

import pytest  # pylint: disable=E0401

from compoconf.nonstrict_dataclass import NonStrictDataclass, asdict
from compoconf.util import MissingValue


# Tests for NonStrictDataclass
def test_non_strict_dataclass_basic_instantiation():
    """Test basic instantiation and attribute access of NonStrictDataclass."""

    @dataclass(init=False)
    class MyNonStrictDataclass(NonStrictDataclass):
        """TestClass"""

        a: int
        b: str = "default_b"

    # Test instantiation with typed and untyped fields
    instance = MyNonStrictDataclass(a=1, c="extra_c", d=3.14)

    # Verify typed fields
    assert instance.a == 1
    assert instance.b == "default_b"

    # Verify untyped fields
    assert instance.c == "extra_c"  # pylint: disable=E1101
    assert instance.d == 3.14  # pylint: disable=E1101

    # Verify that extra fields are stored in _extras
    assert instance._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212

    # Test instantiation with only typed fields
    instance_typed_only = MyNonStrictDataclass(a=2)
    assert instance_typed_only.a == 2
    assert instance_typed_only.b == "default_b"
    assert not instance_typed_only._extras  # pylint: disable=W0212

    # Test instantiation with explicit default override
    instance_override_default = MyNonStrictDataclass(a=3, b="overridden_b")
    assert instance_override_default.a == 3
    assert instance_override_default.b == "overridden_b"
    assert not instance_override_default._extras  # pylint: disable=W0212

    # Test instantiation with extra fields and explicit default override
    instance_extra_override = MyNonStrictDataclass(a=4, b="overridden_b", e="extra_e")
    assert instance_extra_override.a == 4
    assert instance_extra_override.b == "overridden_b"
    assert instance_extra_override.e == "extra_e"  # pylint: disable=E1101
    assert instance_extra_override._extras == {"e": "extra_e"}  # pylint: disable=W0212


def test_non_strict_dataclass_instantiation_missing():
    """Test basic instantiation and attribute access of NonStrictDataclass."""

    @dataclass(init=False)
    class MyNonStrictDataclass1(NonStrictDataclass):
        """TestClass"""

        a: int = MISSING
        c1: str = field(default=MISSING)
        d1: str = field(default_factory=MISSING)
        b: str = "a"
        c2: str = field(default="c2")
        d2: str = field(default_factory=lambda: "abc")

    # Test instantiation with typed and untyped fields
    instance = MyNonStrictDataclass1(1, "c1", "d1", b="b", e="bcd")
    assert asdict(instance) == {
        "a": 1,
        "b": "b",
        "c1": "c1",
        "c2": "c2",
        "d1": "d1",
        "d2": "abc",
        "e": "bcd",
        "_non_strict": True,
    }

    with pytest.raises(TypeError):
        _ = MyNonStrictDataclass1(a=1, c1="c1")


def test_non_strict_dataclass_recursion():
    """
    Test recursion in asdict results in errors.
    """

    @dataclass
    class RecursiveClass:
        """TestClass"""

        a: int = 1
        b: Any = None

    c = RecursiveClass()
    c.b = c

    with pytest.raises(TypeError):
        asdict(c)


def test_asdict_types():
    """
    Test different field types for asdict conversion.
    """

    @dataclass(init=False)
    class MyNonStrictDataclass3(NonStrictDataclass):
        """TestClass"""

        a: list[int] = field(default_factory=lambda: [1, 2, 3])
        b: tuple[int, str] = (1, "1")

    assert asdict(MyNonStrictDataclass3(c=(2, 3))) == {"_non_strict": True, "a": [1, 2, 3], "b": (1, "1"), "c": (2, 3)}


def test_post_init():
    """Test __post_init__ for NonStrictDataclass"""

    @dataclass(init=False)
    class NonStrictWithPostInit(NonStrictDataclass):
        """TestClass"""

        a: int = MissingValue
        b: str = "default_b"

        def __post_init__(self):
            if self.a is MissingValue:
                self.a = 3

    assert NonStrictWithPostInit(b="b", c="c").a == 3


def test_non_strict_dataclass_to_dict():
    """Test the to_dict method of NonStrictDataclass."""

    @dataclass(init=False)
    class MyNonStrictDataclass2(NonStrictDataclass):
        """TestClass"""

        a: int
        b: str = "default_b"

    instance = MyNonStrictDataclass2(a=1, c="extra_c", d=3.14)

    # Test to_dict without extras_key
    dict_representation = asdict(instance)
    assert dict_representation == {"a": 1, "b": "default_b", "c": "extra_c", "d": 3.14, "_non_strict": True}

    # Test asdict with patched asdict
    # Assuming the patch makes asdict behave like to_dict for NonStrictDataclass
    asdict_representation = asdict(instance)
    assert asdict_representation == {"a": 1, "b": "default_b", "c": "extra_c", "d": 3.14, "_non_strict": True}

    # Test to_dict with extras_key
    dict_representation_with_key = instance._to_dict(extras_key="extra_data")  # pylint: disable=W0212
    assert dict_representation_with_key == {
        "a": 1,
        "b": "default_b",
        "extra_data": {"c": "extra_c", "d": 3.14},
        "_non_strict": True,
    }

    # Test to_dict with an instance that has no extra fields
    instance_no_extras = MyNonStrictDataclass2(a=2)
    dict_no_extras = asdict(instance_no_extras)
    assert dict_no_extras == {"a": 2, "b": "default_b", "_non_strict": True}

    dict_no_extras_with_key = asdict(instance_no_extras)
    assert dict_no_extras_with_key == {"a": 2, "b": "default_b", "_non_strict": True}
