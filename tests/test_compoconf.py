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
    LazyConfigUnion,
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

    # cfgtype always returns LazyConfigUnion; the annotation stores that proxy
    annotation = TestConfig2.__annotations__["test"]  # pylint: disable=E1101
    assert isinstance(annotation, LazyConfigUnion)
    assert TestConfig in annotation.__constraints__
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

    lazy = EmptyInterface.cfgtype
    assert isinstance(lazy, LazyConfigUnion)
    # Warning is deferred until constraints are actually resolved
    _ = lazy.__constraints__
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

    # Always returns a LazyConfigUnion, even with a single registered class
    lazy = SingleClassInterface.cfgtype
    assert isinstance(lazy, LazyConfigUnion)
    assert lazy.__constraints__ == (SingleConfig,)
    assert lazy.registry_class is SingleClassInterface
    assert lazy.is_config_type is True


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

    # cfgtype returns a LazyConfigUnion with all registered config classes
    interface_type = MultiClassInterface.cfgtype
    assert isinstance(interface_type, LazyConfigUnion)
    assert hasattr(interface_type, "__constraints__")
    assert Config1 in interface_type.__constraints__
    assert Config2 in interface_type.__constraints__
    assert hasattr(interface_type, "registry_class")
    assert interface_type.registry_class is MultiClassInterface
    assert hasattr(interface_type, "is_config_type")
    assert interface_type.is_config_type is True


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

    # Constraints should contain only ValidConfig (NoConfigClass has no config)
    interface_type = MixedInterface.cfgtype
    assert isinstance(interface_type, LazyConfigUnion)
    assert interface_type.__constraints__ == (ValidConfig,)


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


def test_classproperty_direct_callable():
    from compoconf.compoconf import classproperty  # pylint: disable=C0415

    class Example:
        @classproperty
        def value(cls):  # pylint: disable=E0213
            return "value"

    assert Example.value == "value"  # pylint: disable=W0143


def test_classproperty_without_wrapped():
    from compoconf.compoconf import classproperty

    class Dummy:
        fget = object()

    result = classproperty.__get__(Dummy(), None, type("Owner", (), {}))
    assert result is None


def test_reregistration_warning_when_replacing_class(reset_registry, caplog):
    @register_interface
    class BaseInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class ExampleConfig(ConfigInterface):
        value: int = 1

    @register
    class Original(BaseInterface):
        config: ExampleConfig

    replacement = type("Original", (BaseInterface,), {"config": ExampleConfig})
    caplog.clear()
    with caplog.at_level("WARNING"):
        Registry._reregistration_warnings(ExampleConfig, replacement, "Original", BaseInterface)

    assert "Re-Registering Original" in caplog.text


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
    result = config._to_dict()

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


def test_lazy_config_union_deferred_registration(reset_registry):
    """Test that LazyConfigUnion resolves classes registered AFTER cfgtype is accessed.

    This is the core use case: .cfgtype is used as a field annotation at dataclass
    definition time, before all implementations are registered. The LazyConfigUnion
    proxy should resolve correctly at parse time when all implementations are available.
    """
    from compoconf.parsing import parse_config

    @register_interface
    class MixerInterface(RegistrableConfigInterface):
        pass

    # Access cfgtype BEFORE any implementations are registered
    lazy = MixerInterface.cfgtype
    assert isinstance(lazy, LazyConfigUnion)
    assert lazy.__constraints__ == ()  # nothing registered yet

    # Use it as a field annotation (simulates the import-order scenario)
    @dataclass
    class ContainerConfig:
        mixer: MixerInterface.cfgtype  # captured at class definition time

    # NOW register implementations (simulates later imports)
    @dataclass
    class AttentionConfig(ConfigInterface):
        heads: int = 8

    @register
    class Attention(MixerInterface):
        config: AttentionConfig

    @dataclass
    class ConvConfig(ConfigInterface):
        kernel_size: int = 3

    @register
    class Conv(MixerInterface):
        config: ConvConfig

    # LazyConfigUnion should now resolve both implementations
    assert AttentionConfig in lazy.__constraints__
    assert ConvConfig in lazy.__constraints__

    # parse_config should work correctly despite deferred registration
    cfg = parse_config(ContainerConfig, {"mixer": {"class_name": "Attention", "heads": 12}})
    assert isinstance(cfg.mixer, AttentionConfig)
    assert cfg.mixer.heads == 12

    cfg = parse_config(ContainerConfig, {"mixer": {"class_name": "Conv", "kernel_size": 5}})
    assert isinstance(cfg.mixer, ConvConfig)
    assert cfg.mixer.kernel_size == 5


def test_lazy_config_union_repr(reset_registry):
    """Test LazyConfigUnion repr."""

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    lazy = TestInterface.cfgtype
    assert "LazyConfigUnion" in repr(lazy)
    assert "TestInterface" in repr(lazy)
    assert "empty" in repr(lazy)  # no registrations yet

    @dataclass
    class TestConfig(ConfigInterface):
        pass

    @register
    class TestImpl(TestInterface):
        config: TestConfig

    assert "TestConfig" in repr(lazy)


def test_lazy_config_union_eq_hash(reset_registry):
    """Test LazyConfigUnion equality and hashing."""

    @register_interface
    class Interface1(RegistrableConfigInterface):
        pass

    @register_interface
    class Interface2(RegistrableConfigInterface):
        pass

    lazy1a = Interface1.cfgtype
    lazy1b = Interface1.cfgtype
    lazy2 = Interface2.cfgtype

    # Same interface -> equal
    assert lazy1a == lazy1b
    # Different interface -> not equal
    assert lazy1a != lazy2
    # Not equal to non-LazyConfigUnion
    assert lazy1a != "not a lazy union"
    # Hashable (can be used in sets/dicts)
    assert hash(lazy1a) == hash(lazy1b)
    assert {lazy1a, lazy1b} == {lazy1a}


def test_lazy_config_union_no_registry():
    """Test that cfgtype returns None for unregistered interfaces."""

    class UnregisteredInterface(RegistrableConfigInterface):
        pass

    assert UnregisteredInterface.cfgtype is None


def test_lazy_config_union_direct_parse(reset_registry):
    """Test calling parse_config directly with a LazyConfigUnion as config_class."""
    from compoconf.parsing import parse_config

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class Config1(ConfigInterface):
        value: int = 1

    @register
    class Impl1(TestInterface):
        config: Config1

    @dataclass
    class Config2(ConfigInterface):
        name: str = "test"

    @register
    class Impl2(TestInterface):
        config: Config2

    # Parse directly with the LazyConfigUnion (not wrapped in a dataclass)
    result = parse_config(TestInterface.cfgtype, {"class_name": "Impl1", "value": 42})
    assert isinstance(result, Config1)
    assert result.value == 42

    result = parse_config(TestInterface.cfgtype, {"class_name": "Impl2", "name": "hello"})
    assert isinstance(result, Config2)
    assert result.name == "hello"


def test_lazy_config_union_constraints_no_registry(reset_registry):
    """Test __constraints__ returns () when the interface registry is removed after creation."""

    @register_interface
    class TempInterface(RegistrableConfigInterface):
        pass

    lazy = TempInterface.cfgtype
    # Remove the registry to simulate no-registry state
    Registry._registries.pop(Registry._unique_name(TempInterface))
    assert lazy.__constraints__ == ()


def test_lazy_config_union_constraints_skips_none_config(reset_registry):
    """Test __constraints__ skips registered classes whose config class is None."""

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class ValidConfig(ConfigInterface):
        value: int = 1

    @register
    class ValidImpl(TestInterface):
        config: ValidConfig

    # Manually inject a class with no proper config into the registry
    class NoConfigClass(TestInterface):
        pass

    Registry._registries[Registry._unique_name(TestInterface)]["NoConfigClass"] = NoConfigClass

    lazy = LazyConfigUnion(TestInterface)
    constraints = lazy.__constraints__
    assert ValidConfig in constraints
    assert len(constraints) == 1  # NoConfigClass was skipped


def test_lazy_config_union_or_none(reset_registry):
    """Test SomeInterface.cfgtype | None as a field annotation with parse_config."""
    from compoconf.compoconf import _LazyOr
    from compoconf.parsing import parse_config

    @register_interface
    class MixerInterface(RegistrableConfigInterface):
        pass

    # Access cfgtype BEFORE registrations (the deferred case)
    lazy = MixerInterface.cfgtype

    # Create the optional type
    optional_type = lazy | None
    assert isinstance(optional_type, _LazyOr)

    # Use as a field annotation
    @dataclass
    class ContainerConfig:
        mixer: MixerInterface.cfgtype | None = None

    # NOW register implementations
    @dataclass
    class AttentionConfig(ConfigInterface):
        heads: int = 8

    @register
    class Attention(MixerInterface):
        config: AttentionConfig

    # Parse with a concrete value
    cfg = parse_config(ContainerConfig, {"mixer": {"class_name": "Attention", "heads": 12}})
    assert isinstance(cfg.mixer, AttentionConfig)
    assert cfg.mixer.heads == 12

    # Parse with None
    cfg = parse_config(ContainerConfig, {"mixer": None})
    assert cfg.mixer is None

    # Parse with field absent (uses default None)
    cfg = parse_config(ContainerConfig, {})
    assert cfg.mixer is None


def test_lazy_config_union_or_type(reset_registry):
    """Test SomeInterface.cfgtype | SomeOtherType."""
    from compoconf.compoconf import _LazyOr
    from compoconf.parsing import parse_config

    @register_interface
    class MixerInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class FallbackConfig:
        fallback: bool = True

    @dataclass
    class ContainerConfig:
        mixer: MixerInterface.cfgtype | FallbackConfig

    # Register an implementation after the annotation was created
    @dataclass
    class ConvConfig(ConfigInterface):
        kernel: int = 3

    @register
    class Conv(MixerInterface):
        config: ConvConfig

    # Parse into registered type
    cfg = parse_config(ContainerConfig, {"mixer": {"class_name": "Conv", "kernel": 5}})
    assert isinstance(cfg.mixer, ConvConfig)

    # Parse into the other union member
    cfg = parse_config(ContainerConfig, {"mixer": {"fallback": False}})
    assert isinstance(cfg.mixer, FallbackConfig)
    assert cfg.mixer.fallback is False


def test_lazy_config_union_or_chaining(reset_registry):
    """Test chaining: SomeInterface.cfgtype | None | int and _LazyOr | None."""
    from compoconf.compoconf import _LazyOr

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    lazy = TestInterface.cfgtype
    result = lazy | None | int
    assert isinstance(result, _LazyOr)
    assert type(None) in result.__args__
    assert int in result.__args__

    # _LazyOr.__or__ with None (the None→type(None) conversion in _LazyOr)
    result2 = (lazy | int) | None
    assert isinstance(result2, _LazyOr)
    assert type(None) in result2.__args__
    assert int in result2.__args__


def test_lazy_config_union_ror(reset_registry):
    """Test reversed: None | SomeInterface.cfgtype (multi-class → LazyConfigUnion)."""
    from compoconf.compoconf import _LazyOr
    from compoconf.parsing import parse_config

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class Config1(ConfigInterface):
        value: int = 1

    @register
    class Impl1(TestInterface):
        config: Config1

    @dataclass
    class Config2(ConfigInterface):
        name: str = "x"

    @register
    class Impl2(TestInterface):
        config: Config2

    # None | LazyConfigUnion triggers __ror__ with None→type(None) conversion
    result = None | TestInterface.cfgtype
    assert isinstance(result, _LazyOr)
    assert type(None) in result.__args__

    # Should be parseable
    parsed = parse_config(result, {"class_name": "Impl1", "value": 42})
    assert isinstance(parsed, Config1)
    assert parsed.value == 42

    parsed = parse_config(result, None)
    assert parsed is None

    # type(None) | LazyConfigUnion: __ror__ with non-None other (the else branch)
    result_typed = type(None) | TestInterface.cfgtype
    assert isinstance(result_typed, _LazyOr)
    assert type(None) in result_typed.__args__

    # None | _LazyOr (triggers _LazyOr.__ror__ with None)
    lazy_or = TestInterface.cfgtype | int
    result2 = None | lazy_or
    assert isinstance(result2, _LazyOr)
    assert type(None) in result2.__args__
    assert int in result2.__args__

    # type(None) | _LazyOr (triggers _LazyOr.__ror__ with non-None)
    result3 = type(None) | lazy_or
    assert isinstance(result3, _LazyOr)
    assert type(None) in result3.__args__


def test_lazy_or_repr(reset_registry):
    """Test _LazyOr repr."""
    from compoconf.compoconf import _LazyOr

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class Config1(ConfigInterface):
        pass

    @register
    class Impl1(TestInterface):
        config: Config1

    @dataclass
    class Config2(ConfigInterface):
        pass

    @register
    class Impl2(TestInterface):
        config: Config2

    # Multi-class: cfgtype returns LazyConfigUnion → | None produces _LazyOr
    result = TestInterface.cfgtype | None
    assert isinstance(result, _LazyOr)
    r = repr(result)
    assert "_LazyOr" in r
    assert "NoneType" in r


def test_lazy_config_union_or_single_class(reset_registry):
    """Test cfgtype | None with single class — cfgtype returns LazyConfigUnion, | None produces _LazyOr."""
    from compoconf.compoconf import _LazyOr
    from compoconf.parsing import parse_config

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        value: int = 1

    @register
    class TestImpl(TestInterface):
        config: TestConfig

    # cfgtype always returns LazyConfigUnion, | None produces _LazyOr
    optional_type = TestInterface.cfgtype | None
    assert isinstance(optional_type, _LazyOr)
    assert TestConfig in optional_type.__args__
    assert type(None) in optional_type.__args__

    # parse_config handles _LazyOr
    parsed = parse_config(optional_type, {"class_name": "TestImpl", "value": 42})
    assert isinstance(parsed, TestConfig)
    assert parsed.value == 42

    parsed = parse_config(optional_type, None)
    assert parsed is None


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613,C0415,W0612
