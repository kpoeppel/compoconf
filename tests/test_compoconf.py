"""
Tests for CompoConf
"""

# pylint: disable=R0801

import json
from dataclasses import dataclass, field
from typing import Dict

import pytest  # pylint: disable=E0401

from compoconf.compoconf import (
    ConfigInterface,
    NonStrictDataclass,
    RegistrableConfigInterface,
    Registry,
    register,
    register_interface,
)


# pylint: disable=C0115,C0116,W0212,W0621,W0613,C0415,W0612
@pytest.fixture
def reset_registry():
    """Reset the registry before each test."""
    for reg in list(Registry._registries):
        Registry._registries.pop(reg)
    for reg in list(Registry._registry_classes):
        Registry._registry_classes.pop(reg)
    yield


# Tests for basic registration and configuration
def test_interface_registration(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):  # pylint: disable=W0612
        pass

    assert "TestInterface" in str(Registry)


def test_registration(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        param_a: int = 1

    @register
    class TestClass(TestInterface):  # pylint: disable=W0612
        config: TestConfig

    assert "TestClass" in str(Registry)
    registry_dict = json.loads(str(Registry))
    reg_key = [k for k in list(registry_dict) if k.endswith("TestInterface")]
    assert len(reg_key) == 1
    assert "TestClass" in registry_dict[reg_key[0]]


def test_config_class(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        param_a: int = 1

    @register
    class TestClass(TestInterface):  # pylint: disable=W0612
        config: TestConfig

    assert TestConfig.class_name == "TestClass"


def test_config_class_instantiation(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        param_a: int = 1

    @register
    class TestClass(TestInterface):
        config: TestConfig

    TestConfig.class_name = TestConfig.class_name

    assert Registry.get_class(TestInterface, "TestClass") == TestClass

    instance = TestConfig().instantiate(TestInterface)

    assert isinstance(instance, TestClass)


def test_config_class_instantiation_error(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        param_a: int = 1

    with pytest.raises(ValueError, match="has no instantiation class"):
        _ = TestConfig().instantiate(TestInterface)


def test_config_class_nested(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        pass

    @register
    class TestClass(TestInterface):  # pylint: disable=W0612
        config: TestConfig

    @dataclass
    class TestConfig2(ConfigInterface):
        test: TestInterface.cfgtype = field(default_factory=TestConfig)

    cfg = TestConfig2()
    instance = cfg.test.instantiate(TestInterface)

    # note that type annotations only work if the classes have been registered before
    # otherwise
    assert TestConfig2.__annotations__["test"] == TestConfig  # pylint: disable=E1101
    assert issubclass(TestConfig, TestInterface.cfgtype)
    assert isinstance(instance, TestClass)


def test_reregister(reset_registry, caplog):
    """Test warning when re-registering an interface."""
    import logging

    caplog.set_level(logging.WARNING)

    @register_interface
    class TestInterface(RegistrableConfigInterface):  # pylint: disable=W0612
        pass

    @dataclass
    class TestConfig(ConfigInterface):  # pylint: disable=W0612
        pass

    # pylint: disable=E0102
    @register_interface
    class TestInterface(RegistrableConfigInterface):  # noqa: F811
        pass

    # pylint: enable=E0102

    assert "Tried to re-register registry with interface name" in caplog.text


def test_reregister_class(reset_registry, caplog):
    import logging

    caplog.set_level(logging.WARNING)

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        pass

    @register
    class TestClass(TestInterface):  # pylint: disable=W0612
        config_class = TestConfig

    # pylint: disable=E0102
    @register
    class TestClass(TestInterface):  # noqa: F811
        config: TestConfig

    # pylint: enable=E0102

    assert "Tried to re-register class" in caplog.text


# this test is ignored for now as it inhibits using a registry class also as registered config
# same problem for decorators
# In this case the parent class is first set as the class_name attribute, and only later the correct
# one is set. Maybe there is another way to emit a warning for re-registrations?
#
# def test_reregister_with_different_classname(reset_registry, caplog):
#     """Test re-registering with a different class_name."""
#     import logging

#     caplog.set_level(logging.WARNING)

#     @register_interface
#     class TestInterface(RegistrableConfigInterface):
#         pass

#     @dataclass
#     class TestConfig(ConfigInterface):
#         pass

#     # First registration
#     @register
#     class TestClass(TestInterface):
#         config: TestConfig

#     # Second registration with same config but different class name
#     # This should trigger the warning about re-registering with a different class_name
#     @register
#     class TestClass2(TestInterface):  # pylint: disable=W0612
#         config: TestConfig

#     assert "re-registering" in caplog.text or "previous class_name" in caplog.text


def test_no_interface(reset_registry):
    class TestClass:
        pass

    with pytest.raises(KeyError):
        Registry.get_class(TestClass, "doesn't matter")


def test_no_class(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    with pytest.raises(KeyError):
        Registry.get_class(TestInterface, "NoSuchClass")


def test_no_options_warning(reset_registry, caplog):
    import logging

    caplog.set_level(logging.WARNING)

    @register_interface
    class EmptyInterface(RegistrableConfigInterface):
        pass

    _ = EmptyInterface.cfgtype
    assert "No option for this type" in caplog.text


def test_missing_config_class(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    class TestClassNoConfig(TestInterface):
        pass

    with pytest.raises(RuntimeError, match="does not have a proper config class"):
        register(TestClassNoConfig)


def test_empty_registry_str(reset_registry):
    # Create a new empty registry for testing
    empty_registry = Registry
    assert str(empty_registry) == "{}"


# Tests for classproperty and other utility functions


def test_get_config_class_fallbacks():
    """Test _get_config_class fallback paths."""
    from compoconf.compoconf import _get_config_class

    # Test when class has config attribute but not in type hints
    class ConfigClass:
        class_name = "ConfigClass"

    class TestClass:
        config: None
        config = ConfigClass()

    # This should return None since config is not in type hints
    assert _get_config_class(TestClass) is None


def test_registrable_config_interface_init():
    """Test RegistrableConfigInterface.__init__."""

    # Test initialization with args and kwargs
    instance = RegistrableConfigInterface(1, 2, 3, a=1, b=2)
    assert isinstance(instance, RegistrableConfigInterface)


def test_registry_type_no_registry():
    """Test RegistrableConfigInterface.cfgtype when no registry exists."""

    # Create a class that doesn't have a registry
    class NoRegistryInterface(RegistrableConfigInterface):
        pass

    # This should return None since there's no registry
    assert NoRegistryInterface.cfgtype is None


def test_registry_type_single_class(reset_registry):
    """Test RegistrableConfigInterface.cfgtype with a single registered class."""

    @register_interface
    class SingleClassInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class SingleConfig(ConfigInterface):
        value: int = 1

    @register
    class SingleImpl(SingleClassInterface):
        config: SingleConfig

    # This should return the config class directly, not a TypeVar
    assert SingleClassInterface.cfgtype is SingleConfig
    assert hasattr(SingleClassInterface.cfgtype, "registry_class")
    assert hasattr(SingleClassInterface.cfgtype, "is_config_type")


def test_registry_type_multiple_classes(reset_registry):
    """Test RegistrableConfigInterface.cfgtype with multiple registered classes."""

    @register_interface
    class MultiClassInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class Config1(ConfigInterface):
        value: int = 1

    @dataclass
    class Config2(ConfigInterface):
        name: str = "test"

    @register
    class Impl1(MultiClassInterface):
        config: Config1

    @register
    class Impl2(MultiClassInterface):
        config: Config2

    # This should return a TypeVar since there are multiple config classes
    interface_type = MultiClassInterface.cfgtype
    assert hasattr(interface_type, "__constraints__")
    assert Config1 in interface_type.__constraints__
    assert Config2 in interface_type.__constraints__
    assert hasattr(interface_type, "registry_class")
    assert hasattr(interface_type, "is_config_type")


def test_registry_type_with_none_config(reset_registry):
    """Test RegistrableConfigInterface.cfgtype with a class that has no config."""

    @register_interface
    class MixedInterface(RegistrableConfigInterface):
        pass

    # Create a class that will be registered but doesn't have a proper config
    class NoConfigClass(MixedInterface):
        # This class has no config_class or config attribute
        pass

    # Manually add the class to the registry to bypass the normal registration
    # which would raise an error for missing config_class
    Registry._registries[Registry._unique_name(MixedInterface)]["NoConfigClass"] = NoConfigClass

    @dataclass
    class ValidConfig(ConfigInterface):
        value: int = 1

    @register
    class ValidImpl(MixedInterface):
        config: ValidConfig

    # This should still return ValidConfig and ignore NoConfigClass
    interface_type = MixedInterface.cfgtype
    assert interface_type is ValidConfig


def test_registry_str_formatting(reset_registry):
    """Test Registry.__str__ formatting with different registry states."""
    # Empty registry
    assert str(Registry) == "{}"

    # Registry with empty classes
    @register_interface
    class EmptyInterface(RegistrableConfigInterface):
        pass

    # This should format correctly with empty classes
    assert "[]" in str(Registry)

    # Registry with classes
    @dataclass
    class TestConfig(ConfigInterface):
        pass

    @register
    class TestImpl(EmptyInterface):
        config: TestConfig

    # This should format correctly with classes
    assert "TestImpl" in str(Registry)

    # Test with multiple registries to ensure newlines are handled correctly
    @register_interface
    class AnotherInterface(RegistrableConfigInterface):
        pass

    registry_str = str(Registry)
    assert "\n" in registry_str
    assert "}" in registry_str


def test_config_interface_reduce_setstate():
    """Test ConfigInterface.__reduce__ and __setstate__ methods."""

    @dataclass
    class TestReduceConfig(ConfigInterface):
        value: int = 42
        name: str = "test"

    # Create an instance
    config = TestReduceConfig(value=100, name="reduced")

    # Call __reduce__ directly
    reduced = config.__reduce__()

    # Check the structure of the reduced tuple
    assert len(reduced) == 3
    assert reduced[0] is TestReduceConfig  # class
    assert not reduced[1]  # args, == ()
    assert isinstance(reduced[2], dict)  # state
    assert reduced[2]["value"] == 100
    assert reduced[2]["name"] == "reduced"

    # Create a new instance and restore state
    new_config = TestReduceConfig()
    new_config.__setstate__(reduced[2])

    # Check that state was restored correctly
    assert new_config.value == 100
    assert new_config.name == "reduced"


def test_config_interface_to_dict():
    """Test ConfigInterface.to_dict method."""

    @dataclass
    class TestDictConfig(ConfigInterface):
        value: int = 42
        name: str = "test"
        nested: Dict[str, int] = field(default_factory=lambda: {"a": 1, "b": 2})

    # Create an instance
    config = TestDictConfig(value=100, name="dict_test")

    # Call to_dict
    result = config.to_dict()

    # Check the result
    assert isinstance(result, dict)
    assert result["value"] == 100
    assert result["name"] == "dict_test"
    assert result["nested"] == {"a": 1, "b": 2}
    assert result["class_name"] == ""  # Default value


def test_invalid_registry_class_type(reset_registry):
    """Test that a class with an invalid config type raises an error."""
    with pytest.raises(RuntimeError, match="Tried to create registry"):

        @register_interface
        class InvalidConfigInterface:
            pass


# Tests for NonStrictDataclass
def test_non_strict_dataclass_basic_instantiation():
    """Test basic instantiation and attribute access of NonStrictDataclass."""

    @dataclass(init=False)
    class MyNonStrictDataclass(NonStrictDataclass):
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
    assert instance._extras == {"c": "extra_c", "d": 3.14}

    # Test instantiation with only typed fields
    instance_typed_only = MyNonStrictDataclass(a=2)
    assert instance_typed_only.a == 2
    assert instance_typed_only.b == "default_b"
    assert not instance_typed_only._extras

    # Test instantiation with explicit default override
    instance_override_default = MyNonStrictDataclass(a=3, b="overridden_b")
    assert instance_override_default.a == 3
    assert instance_override_default.b == "overridden_b"
    assert not instance_override_default._extras

    # Test instantiation with extra fields and explicit default override
    instance_extra_override = MyNonStrictDataclass(a=4, b="overridden_b", e="extra_e")
    assert instance_extra_override.a == 4
    assert instance_extra_override.b == "overridden_b"
    assert instance_extra_override.e == "extra_e"  # pylint: disable=E1101
    assert instance_extra_override._extras == {"e": "extra_e"}


def test_non_strict_dataclass_instantiation_missing():
    """Test basic instantiation and attribute access of NonStrictDataclass."""
    from dataclasses import MISSING

    @dataclass(init=False)
    class MyNonStrictDataclass1(NonStrictDataclass):
        a: int = MISSING
        c1: str = field(default=MISSING)
        d1: str = field(default_factory=MISSING)
        b: str = "a"
        c2: str = field(default="c2")
        d2: str = field(default_factory=lambda: "abc")

    # Test instantiation with typed and untyped fields
    instance = MyNonStrictDataclass1(1, "c1", "d1", b="b", e="bcd")
    assert instance.to_dict() == {
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


def test_non_strict_dataclass_to_dict():
    """Test the to_dict method of NonStrictDataclass."""

    @dataclass(init=False)
    class MyNonStrictDataclass2(NonStrictDataclass):
        a: int
        b: str = "default_b"

    instance = MyNonStrictDataclass2(a=1, c="extra_c", d=3.14)

    # Test to_dict without extras_key
    dict_representation = instance.to_dict()
    assert dict_representation == {"a": 1, "b": "default_b", "c": "extra_c", "d": 3.14, "_non_strict": True}

    # Test to_dict with extras_key
    dict_representation_with_key = instance.to_dict(extras_key="extra_data")
    assert dict_representation_with_key == {
        "a": 1,
        "b": "default_b",
        "extra_data": {"c": "extra_c", "d": 3.14},
        "_non_strict": True,
    }

    # Test to_dict with an instance that has no extra fields
    instance_no_extras = MyNonStrictDataclass2(a=2)
    dict_no_extras = instance_no_extras.to_dict()
    assert dict_no_extras == {"a": 2, "b": "default_b", "_non_strict": True}

    dict_no_extras_with_key = instance_no_extras.to_dict(extras_key="extra_data")
    assert dict_no_extras_with_key == {"a": 2, "b": "default_b", "extra_data": {}, "_non_strict": True}


def test_parse_config_with_non_strict_dataclass():
    """Test parse_config with NonStrictDataclass and extra fields."""
    from compoconf.parsing import parse_config

    @dataclass(init=False)
    class MyNonStrictConfig(NonStrictDataclass):
        typed_field: int
        default_field: str = "default"

    # Data with typed fields and extra untyped fields
    data_with_extras = {
        "typed_field": 123,
        "default_field": "overridden",
        "extra_field_1": "some_value",
        "extra_field_2": 456,
    }

    # Test parsing with strict=True (should still allow extras due to _non_strict)
    parsed_strict = parse_config(MyNonStrictConfig, data_with_extras, strict=True)
    assert isinstance(parsed_strict, MyNonStrictConfig)
    assert parsed_strict.typed_field == 123
    assert parsed_strict.default_field == "overridden"
    # Check that extra fields are accessible as attributes
    assert parsed_strict.extra_field_1 == "some_value"
    assert parsed_strict.extra_field_2 == 456
    # Check that extra fields are stored in _extras
    assert parsed_strict._extras == {"extra_field_1": "some_value", "extra_field_2": 456}

    # Test parsing with strict=False (should also allow extras)
    parsed_non_strict = parse_config(MyNonStrictConfig, data_with_extras, strict=False)
    assert isinstance(parsed_non_strict, MyNonStrictConfig)
    assert parsed_non_strict.typed_field == 123
    assert parsed_non_strict.default_field == "overridden"
    assert parsed_non_strict.extra_field_1 == "some_value"
    assert parsed_non_strict.extra_field_2 == 456
    assert parsed_non_strict._extras == {"extra_field_1": "some_value", "extra_field_2": 456}

    # Test parsing with only typed fields
    data_typed_only = {"typed_field": 789}
    parsed_typed_only = parse_config(MyNonStrictConfig, data_typed_only)
    assert isinstance(parsed_typed_only, MyNonStrictConfig)
    assert parsed_typed_only.typed_field == 789
    assert parsed_typed_only.default_field == "default"
    assert parsed_typed_only._extras == {}

    # Test parsing with missing required field (should raise error)
    data_missing_required = {"default_field": "value"}
    with pytest.raises(TypeError):
        parse_config(MyNonStrictConfig, data_missing_required)

    # Test parsing with extra fields that are not in _extras (should be handled by NonStrictDataclass __init__)
    # The _handle_dataclass logic in parsing.py should correctly pass these to the NonStrictDataclass constructor.
    # The NonStrictDataclass constructor then assigns them to attributes and stores them in _extras.
    # So, the above tests already cover this implicitly.


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613,C0415,W0612
