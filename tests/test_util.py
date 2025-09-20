"""Tests for CompoConf utilities"""

# pylint: disable=R0801

from dataclasses import dataclass, field
from typing import Union

import pytest  # pylint: disable=E0401

try:
    from typing_extensions import dataclass_transform
except ImportError:
    pass

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, Registry, register_interface
from compoconf.util import from_annotations, partial_call

# pylint: disable=E1123,E1121,E1101  # to circumvent these pylint errors, use stubs (generated pyi files)
# pylint: disable=C0115,C0116,W0212,W0621,W0613,R0801


class Array:
    def __init__(self, x):
        self._x = x

    def __add__(self, x: Union[int, "Array"]) -> "Array":
        if isinstance(x, Array):
            return Array([y + z for y, z in zip(self, x)])
        if isinstance(x, int):
            return Array([y + x for y in self._x])
        raise ValueError

    def __mul__(self, x: Union[int, "Array"]) -> "Array":
        if isinstance(x, Array):
            return Array([y * z for y, z in zip(self, x)])
        if isinstance(x, int):
            return Array([y * x for y in self])
        raise ValueError

    def __eq__(self, x: object) -> bool:
        if isinstance(x, Array):
            return all(z == y for y, z in zip(self, x))
        if isinstance(x, int):
            return all(y == x for y in self)
        return False

    def __iter__(self):
        return iter(self._x)


@pytest.fixture
def array_func():
    """Reset Registry and register the interface for each test."""
    # Reset Registry for each test
    for reg in list(Registry._registries):
        Registry._registries.pop(reg)
    for reg in list(Registry._registry_classes):
        Registry._registry_classes.pop(reg)

    # Register the interface for each test
    @register_interface
    class ArrayFunc(RegistrableConfigInterface):
        def __call__(self, x: Array) -> Array:
            raise NotImplementedError

    return ArrayFunc


def test_partial_call_basic(array_func):
    """Test basic functionality of partial_call with default behavior"""

    def multiply(x, multiplier: int):
        return x * multiplier

    @partial_call(multiply, "Multiply", array_func)
    @dataclass
    class Config(ConfigInterface):
        multiplier: int = 1

    # Test with default value
    func = Config().instantiate(array_func)
    assert func(Array([1])) == Array([1])

    # Test with custom value
    func = Config(multiplier=2).instantiate(array_func)
    assert func(Array([1])) == Array([2])


def test_partial_call_pass_args(array_func):
    """Test partial_call with pass_args parameter"""

    def multiply(x: Array, multiplier: int):
        return x * multiplier

    @partial_call(multiply, "Multiply", array_func, pass_args=[0])
    @dataclass
    class Config(ConfigInterface):
        multiplier: int = 2

    func = Config().instantiate(array_func)
    assert func(Array([1])) == Array([2])


def test_partial_call_pass_kwargs(array_func):
    """Test partial_call with pass_kwargs parameter"""

    def multiply(x: Array, multiplier: int):
        return x * multiplier

    @partial_call(multiply, "Multiply", array_func, pass_kwargs=["x"])
    @dataclass
    class Config(ConfigInterface):
        multiplier: int = 3

    func = Config().instantiate(array_func)
    assert func(x=Array([1])) == Array([3])


def test_partial_call_cfg_args(array_func):
    """Test partial_call with cfg_args parameter"""

    def multiply(x: Array, multiplier: int):
        return x * multiplier

    @partial_call(multiply, "Multiply", array_func, cfg_args=[1])
    @dataclass
    class Config(ConfigInterface):
        multiplier: int = 4

    func = Config().instantiate(array_func)
    assert func(Array([1])) == Array([4])


def test_partial_call_default_values(array_func):
    """Test partial_call with function having default values"""

    def add_offset(x: Array, offset: int = 0):
        return x + offset

    @partial_call(add_offset, "AddOffset", array_func)
    @dataclass
    class Config(ConfigInterface):
        pass

    # Test with default value
    func = Config().instantiate(array_func)
    assert func(Array([1])) == Array([1])


def test_partial_call_default_as_pass_args(array_func):
    """Test that default_as_pass_args controls parameter handling"""

    def complex_func(a: int = 1, b: int = 2, c: int = 3):
        return a + b + c

    # When default_as_pass_args=True (default), non-cfg params are passed through
    @partial_call(complex_func, "Complex1", array_func, cfg_kwargs=["a"])
    @dataclass
    class Config1(ConfigInterface):
        pass

    func1 = Config1(a=1).instantiate(array_func)
    assert func1(2, 3) == 6  # b,c passed through

    # When default_as_pass_args=False, existing config attributes are used
    @partial_call(complex_func, "Complex2", array_func, cfg_kwargs=["a"], default_as_pass_args=False)
    @dataclass
    class Config2(ConfigInterface):
        b: int = 5  # This should be used instead of function default

    func2 = Config2(a=1).instantiate(array_func)
    assert func2(c=3) == 9  # b from config, c passed through


def test_partial_call_existing_values(array_func):
    """Test that partial_call preserves existing values when creating dataclass"""

    def complex_func(a: int = 1, b: int = 2):
        return a + b

    @partial_call(complex_func, "Complex", array_func, default_as_pass_args=False)
    @dataclass
    class Config(ConfigInterface):
        a: int = 5  # Override function default

    # Test that existing value is preserved
    config = Config()
    assert config.a == 5  # Should use class default, not function default
    assert config.b == 2  # Should use function default
    assert config.class_name == "Complex"  # Should have class_name field


def test_from_annotations_arg_passing(array_func):
    """Test that from_annotations properly handles both args and kwargs"""

    class ComplexClass:
        def __init__(self, x: int, y: int = 2):
            self.x = x
            self.y = y
            self.sum = x + y

    @dataclass_transform()
    @from_annotations(ComplexClass, "Complex", array_func, default_as_pass_args=True)
    @dataclass
    class Config(ConfigInterface):
        x: int = 1

    # Test positional arg passing
    instance = Config("Complex", 3).instantiate(array_func)
    assert instance.sum == 5  # 3 + 2

    # Test with additional kwargs
    instance = Config(x=3).instantiate(array_func, y=4)
    assert instance.sum == 7  # 3 + 4


def test_partial_call_type_annotations(array_func):
    """Test that type annotations are properly transferred"""

    def multiply(x: Array, multiplier: int):
        return x * multiplier

    @partial_call(multiply, "Multiply", array_func, pass_args=[0])
    @dataclass
    class Config(ConfigInterface):
        pass

    assert Config.__annotations__["multiplier"] is int


def test_from_annotations_basic(array_func):
    """Test basic functionality of from_annotations"""

    class ExternalClass:
        def __init__(self, multiplier: int = 2, offset: int = 0):
            self.multiplier = multiplier
            self.offset = offset

        def __call__(self, x: Array) -> Array:
            return (x * self.multiplier) + self.offset

    @from_annotations(ExternalClass, "Multiply", array_func)
    @dataclass
    class Config(ConfigInterface):
        pass

    # Test with default values
    func = Config().instantiate(array_func)
    assert func(Array([1])) == Array([2])

    # Test with custom values
    func = Config(multiplier=3).instantiate(array_func)
    assert func(Array([1])) == Array([3])


def test_from_annotations_default_as_pass_args(array_func):
    """Test that default_as_pass_args controls parameter handling in from_annotations"""

    class ComplexClass:
        def __init__(self, x: int = 1, y: int = 2, z: int = 3):
            self.x = x
            self.y = y
            self.z = z
            self.sum = x + y + z

    # When default_as_pass_args=False (default), all params become config fields
    @from_annotations(ComplexClass, "Complex1", array_func)
    @dataclass
    class Config1(ConfigInterface):
        pass

    instance1 = Config1(x=4, y=5, z=6).instantiate(array_func)
    assert instance1.sum == 15  # All values from config

    # When default_as_pass_args=True, only existing fields become config fields
    @from_annotations(ComplexClass, "Complex2", array_func, default_as_pass_args=True)
    @dataclass
    class Config2(ConfigInterface):
        x: int = 4  # Only x is in config

    instance2 = Config2(x=4).instantiate(array_func, y=5, z=6)
    assert instance2.sum == 15  # x from config, y,z from kwargs


def test_from_annotations_pass_args(array_func):
    """Test from_annotations with pass_args parameter"""

    class ExternalClass:
        def __init__(self, offset: int, multiplier: int):
            self.offset = offset
            self.multiplier = multiplier

        def __call__(self, x: Array) -> Array:
            return (x * self.multiplier) + self.offset

    @from_annotations(ExternalClass, "Multiply", array_func, pass_args=[0])
    @dataclass
    class Config(ConfigInterface):
        pass

    func = Config(multiplier=1).instantiate(array_func, 2)
    assert func(Array([1])) == Array([3])


def test_from_annotations_pass_kwargs(array_func):
    """Test from_annotations with pass_kwargs parameter"""

    class ExternalClass:
        def __init__(self, offset: int = 0, multiplier: int = 1):
            self.offset = offset
            self.multiplier = multiplier

        def __call__(self, x: Array) -> Array:
            return (x * self.multiplier) + self.offset

    @from_annotations(ExternalClass, "Multiply", array_func, pass_kwargs=["multiplier"])
    @dataclass
    class Config(ConfigInterface):
        pass

    func = Config().instantiate(array_func, multiplier=4)
    assert func(Array([1])) == Array([4])


def test_from_annotations_type_annotations(array_func):
    """Test that type annotations are properly transferred"""

    class ExternalClass:
        def __init__(self, multiplier: int = 2, offset: int = 0):
            self.multiplier = multiplier
            self.offset = offset

        def __call__(self, x: Array) -> Array:
            return (x * self.multiplier) + self.offset

    @from_annotations(ExternalClass, "Multiply", array_func)
    @dataclass
    class Config(ConfigInterface):
        pass

    assert Config.__annotations__["multiplier"] is int
    assert Config.__annotations__["offset"] is int


def test_config_pickling(array_func):
    """Test that all config classes can be pickled and unpickled (for multiprocessing)"""
    import pickle  # pylint: disable=R0914,C0415

    # Test partial_call config
    def add_func(x: int, y: int = 2):
        return x + y

    @partial_call(add_func, "Pickle1", array_func)
    @dataclass
    class Config1(ConfigInterface):
        x: int = 1

    # Create, pickle, and unpickle config
    config1 = Config1(x=3)
    pickled1 = pickle.dumps(config1)
    unpickled1 = pickle.loads(pickled1)

    # Verify unpickled config works and can be instantiated
    func1 = unpickled1.instantiate(array_func)
    assert func1() == 5  # 3 + 2

    # Test pickling of instantiated object
    pickled_func1 = pickle.dumps(func1)
    unpickled_func1 = pickle.loads(pickled_func1)
    assert unpickled_func1() == 5  # Still works after pickling


def test_config_pickling2(array_func):
    """Test that from_annotations config classes can be pickled and unpickled"""
    import pickle  # pylint: disable=R0914,C0415

    # Test from_annotations config
    class AddClass:
        def __init__(self, x: int = 1, y: int = 2):
            self.x = x
            self.y = y

        def __call__(self):
            return self.x + self.y

    @from_annotations(AddClass, "Pickle2", array_func)
    @dataclass
    class Config2(ConfigInterface):
        x: int = 1

    # Create, pickle, and unpickle config
    config2 = Config2(x=3)
    pickled2 = pickle.dumps(config2)
    unpickled2 = pickle.loads(pickled2)

    # Verify unpickled config works and can be instantiated
    func2 = unpickled2.instantiate(array_func)
    assert func2() == 5  # 3 + 2

    # Test pickling of instantiated object
    pickled_func2 = pickle.dumps(func2)
    unpickled_func2 = pickle.loads(pickled_func2)
    assert unpickled_func2() == 5  # Still works after pickling


def test_from_annotations_method_delegation(array_func):
    """Test that methods are properly delegated to the wrapped instance"""

    class ExternalClass:
        def __init__(self, multiplier: int = 2, offset: int = 0):
            self.multiplier = multiplier
            self.offset = offset

        def __call__(self, x: Array) -> Array:
            return (x * self.multiplier) + self.offset

    class ExtendedClass(ExternalClass):
        def extra_method(self, x: int) -> int:
            return x * self.multiplier

    @from_annotations(ExtendedClass, "Extended", array_func)
    @dataclass
    class Config(ConfigInterface):
        pass

    instance = Config(multiplier=2).instantiate(array_func)
    assert instance.extra_method(3) == 6


def test_annotated_template_special_methods(array_func):
    """Test special methods of _AnnotatedTemplate"""

    class Container:
        def __init__(self, items=None):
            self.items = items or []

        def __str__(self):
            return f"Container({self.items})"

        def __repr__(self):
            return f"Container(items={self.items!r})"

        def __len__(self):
            return len(self.items)

        def __iter__(self):
            return iter(self.items)

        def __getitem__(self, key):
            return self.items[key]

        def __setitem__(self, key, value):
            self.items[key] = value

    @from_annotations(Container, "ContainerWrapper", array_func)
    @dataclass
    class ContainerConfig(ConfigInterface):
        items: list = field(default_factory=list)

    # Create an instance with some items
    container = ContainerConfig(items=[1, 2, 3]).instantiate(array_func)

    # Test __str__ method
    assert str(container) == "Container([1, 2, 3])"

    # Test __repr__ method
    assert repr(container).startswith("Container(items=")

    # Test __len__ method
    assert len(container) == 3

    # Test __iter__ method
    assert list(container) == [1, 2, 3]

    # Test __getitem__ method
    assert container[0] == 1
    assert container[1] == 2

    # Test __setitem__ method
    container[0] = 10
    assert container[0] == 10


def test_dynamic_config_protocol():
    """Test DynamicConfig protocol"""
    from compoconf.util import DynamicConfig  # pylint: disable=C0415

    @dataclass
    class CustomConfig:
        class_name: str = "CustomConfig"
        value: int = 42

        def __getattr__(self, name):
            return f"Custom_{name}"

        def __setattr__(self, name, value):
            super().__setattr__(name, value)

    # Check if our class is recognized as a DynamicConfig
    config = CustomConfig()
    assert isinstance(config, DynamicConfig)

    # Test the protocol methods
    config.class_name = "NewName"
    assert config.class_name == "NewName"
    assert getattr(config, "test") == "Custom_test"


def test_configurable_callable_protocol():
    """Test ConfigurableCallable protocol"""
    from compoconf.util import ConfigurableCallable, DynamicConfig  # pylint: disable=C0415

    @dataclass
    class CustomConfig:
        class_name: str = "CustomConfig"
        value: int = 42

        def __getattr__(self, name):
            return f"Custom_{name}"

        def __setattr__(self, name, value):
            super().__setattr__(name, value)

    class CustomCallable:
        def __init__(self):
            self.config = CustomConfig()

        def __call__(self, x, y=1):
            return x + y + self.config.value

    # Check if our class is recognized as a ConfigurableCallable
    callable_obj = CustomCallable()
    assert isinstance(callable_obj.config, DynamicConfig)
    assert isinstance(callable_obj, ConfigurableCallable)

    # Test the protocol methods
    assert callable_obj(10) == 53  # 10 + 1 + 42


def test_validate_literal_field():
    """Test validate_literal_field function"""
    from typing import Literal  # pylint: disable=C0415

    from compoconf.util import validate_literal_field  # pylint: disable=C0415

    @dataclass
    class ConfigWithLiteral:
        mode: Literal["train", "test", "val"] = "train"
        level: int = 1

    # Test with valid value
    config = ConfigWithLiteral(mode="test")
    assert validate_literal_field(config, "mode") is True

    # Test with invalid value (should still return False, not raise)
    config.mode = "invalid"  # type: ignore
    assert validate_literal_field(config, "mode") is False

    # Test with non-Literal field
    with pytest.raises(ValueError, match="not annotated with a Literal"):
        validate_literal_field(config, "level")

    # Test with non-existent field
    with pytest.raises(ValueError, match="not defined in the dataclass"):
        validate_literal_field(config, "nonexistent")

    # Test with non-dataclass object
    with pytest.raises(TypeError, match="not a dataclass instance"):
        validate_literal_field({"mode": "train"}, "mode")


def test_assert_check_literals():
    """Test assert_check_literals function"""
    from typing import Literal  # pylint: disable=C0415

    from compoconf.util import LiteralError, assert_check_literals  # pylint: disable=C0415

    @dataclass
    class ConfigWithLiterals:
        mode: Literal["train", "test", "val"] = "train"
        level: Literal[1, 2, 3] = 1
        name: str = "default"

    # Test with valid values
    config = ConfigWithLiterals(mode="test", level=2)
    assert_check_literals(config)  # Should not raise

    # Test with invalid value
    config.mode = "invalid"  # type: ignore
    with pytest.raises(LiteralError, match="not in"):
        assert_check_literals(config)

    # Reset to valid value
    config.mode = "train"

    # Test another invalid value
    config.level = 4  # type: ignore
    with pytest.raises(LiteralError, match="not in"):
        assert_check_literals(config)

    # Test with non-dataclass object
    with pytest.raises(TypeError, match="not a dataclass instance"):
        assert_check_literals({"mode": "train"})


def test_partial_call_template_class_getitem():
    """Test __class_getitem__ method of _PartialCallTemplate"""
    from compoconf.util import _PartialCallTemplate  # pylint: disable=C0415

    # Create a specialized version of _PartialCallTemplate
    SpecializedTemplate = _PartialCallTemplate[int]

    # Check that it's a proper subclass
    assert issubclass(SpecializedTemplate, _PartialCallTemplate)

    # Check that it has the expected attributes
    assert hasattr(SpecializedTemplate, "__orig_class__")
    assert SpecializedTemplate.__orig_class__ == _PartialCallTemplate


def test_annotated_template_class_getitem():
    """Test __class_getitem__ method of _AnnotatedTemplate"""
    from compoconf.util import _AnnotatedTemplate  # pylint: disable=C0415

    # Create a specialized version of _AnnotatedTemplate
    SpecializedTemplate = _AnnotatedTemplate[str]

    # Check that it's a proper subclass
    assert issubclass(SpecializedTemplate, _AnnotatedTemplate)

    # Check that it has the expected attributes
    assert hasattr(SpecializedTemplate, "__orig_class__")
    assert SpecializedTemplate.__orig_class__ == _AnnotatedTemplate


def test_partial_call_template_branch_paths():
    from compoconf.util import _PartialCallTemplate  # pylint: disable=C0415

    @dataclass
    class SimpleConfig:
        value: int = 3

    class Template(_PartialCallTemplate):
        _fun = staticmethod(lambda value=0: value)
        _param_names = ["value"]
        _param_indices = {"value": 0}
        _pass_param_names = set()
        _cfg_param_names = {"value"}

    instance = Template(SimpleConfig())
    assert instance() == 3

    @dataclass
    class MixedConfig:
        provided: int = 4

    class PassTemplate(_PartialCallTemplate):
        _fun = staticmethod(lambda a=0, provided=0: a + provided)
        _param_names = ["a", "provided"]
        _param_indices = {"a": 0, "provided": 1}
        _pass_param_names = {"a"}
        _cfg_param_names = {"provided"}

    instance_kw = PassTemplate(MixedConfig())
    assert instance_kw(a=6) == 10

    @dataclass
    class EmptyConfig:
        pass

    class MissingTemplate(_PartialCallTemplate):
        _fun = staticmethod(lambda missing=99: missing)
        _param_names = ["missing"]
        _param_indices = {"missing": 0}
        _pass_param_names = set()
        _cfg_param_names = {"missing"}

    instance_missing = MissingTemplate(EmptyConfig())
    assert instance_missing() == 99


def test_annotated_template_branch_paths():
    from compoconf.util import _AnnotatedTemplate  # pylint: disable=C0415

    @dataclass
    class AnnotConfig:
        value: int = 2

    class Wrapped:
        def __init__(self, *, value=0):
            self.value = value

        def __call__(self, increment=0):
            return self.value + increment

    class Template(_AnnotatedTemplate):
        _wrapped_cls = Wrapped
        _params_to_add = {"value", "missing"}

    wrapper = Template(AnnotConfig())
    assert wrapper(increment=3) == 5

    @dataclass
    class ConfigWithClassName(ConfigInterface):
        value: int = 7

    ConfigWithClassName.class_name = "Wrapped"

    class TemplateWithClassName(_AnnotatedTemplate):
        _wrapped_cls = Wrapped
        _params_to_add = {"value"}

    wrapper_with_name = TemplateWithClassName(ConfigWithClassName(value=1))
    assert wrapper_with_name() == 1


def test_assert_check_nonmissing():
    from compoconf.util import ConfigError, MissingValue, assert_check_nonmissing  # pylint: disable=C0415

    @dataclass
    class TestClass5:
        a: int = MissingValue

        def __post_init__(self):
            assert_check_nonmissing(self)

    assert TestClass5(a=5).a == 5

    with pytest.raises(ConfigError):
        TestClass5()

    with pytest.raises(TypeError):
        assert_check_nonmissing(1)


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
# pylint: enable=E1123,E1121,E1101,R0801
