"""
Tests for pickling and copying configs.

Configs travel between processes (multiprocessing pools) and get copied a lot,
and both routes go through the same reduction protocol.
"""

# pylint: disable=R0801

import copy
import pickle
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface


# pylint: disable=C0115,C0116,W0212,W0621,W0613,C0415,W0612,W0201,W0231
@dataclass
class LeafConfig(ConfigInterface):
    depth: int = 2
    label: str = "leaf"


@dataclass
class NestedConfig(ConfigInterface):
    leaf: LeafConfig = field(default_factory=LeafConfig)
    items: list = field(default_factory=lambda: [1, 2])
    mapping: dict = field(default_factory=lambda: {"a": 1})


@dataclass(kw_only=True)
class RequiredFieldConfig(ConfigInterface):
    """A config whose fields have no defaults, so ``cls()`` cannot build it."""

    width: int
    name: str
    optional: Optional[str] = None


@dataclass
class NamedConfig(ConfigInterface):
    scale: float = 1.5


@dataclass(kw_only=True)
class RequiredNestedConfig(ConfigInterface):
    required_leaf: LeafConfig
    count: int


ROUND_TRIPS = [
    pytest.param(lambda obj: pickle.loads(pickle.dumps(obj)), id="pickle"),
    pytest.param(copy.deepcopy, id="deepcopy"),
    pytest.param(copy.copy, id="copy"),
]


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
def test_config_with_required_fields_survives(round_trip):
    """Reconstruction must not go through __init__, which needs those fields."""
    config = RequiredFieldConfig(width=512, name="run")
    restored = round_trip(config)
    assert restored.width == 512
    assert restored.name == "run"
    assert restored.optional is None
    assert restored == config


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
def test_nested_configs_keep_their_type(round_trip):
    """A nested config must come back as a config, not as a plain dict."""
    config = NestedConfig()
    restored = round_trip(config)
    assert isinstance(restored.leaf, LeafConfig)
    assert restored.leaf.depth == 2
    assert restored.leaf.label == "leaf"
    assert restored == config


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
def test_required_nested_config_survives(round_trip):
    config = RequiredNestedConfig(required_leaf=LeafConfig(depth=9), count=3)
    restored = round_trip(config)
    assert isinstance(restored.required_leaf, LeafConfig)
    assert restored.required_leaf.depth == 9
    assert restored.count == 3
    assert restored == config


def test_deep_copy_is_independent():
    """The copy must not share the nested config with the original."""
    config = NestedConfig()
    restored = copy.deepcopy(config)
    restored.leaf.depth = 99
    restored.items.append(3)
    restored.mapping["b"] = 2
    assert config.leaf.depth == 2
    assert config.items == [1, 2]
    assert config.mapping == {"a": 1}


def test_shallow_copy_shares_nested_values():
    """copy.copy stays shallow, as it does for any other dataclass."""
    config = NestedConfig()
    restored = copy.copy(config)
    assert restored.leaf is config.leaf


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
def test_init_false_field_survives(round_trip):
    """class_name is init=False, so any __init__-based rebuild would lose it."""
    config = NamedConfig(scale=2.5)
    config.class_name = "SomeImpl"
    restored = round_trip(config)
    assert restored.class_name == "SomeImpl"
    assert restored.scale == 2.5


@pytest.mark.parametrize("round_trip", [pytest.param(copy.deepcopy, id="deepcopy"), pytest.param(copy.copy, id="copy")])
def test_copied_config_still_instantiates(round_trip, reset_registry):
    """class_name is what instantiate() dispatches on, so it must survive."""

    @register_interface
    class Interface(RegistrableConfigInterface):
        pass

    @dataclass
    class ImplConfig(ConfigInterface):
        scale: float = 1.5

    @register
    class Impl(Interface):
        config: ImplConfig

        def __init__(self, config: Any):
            self.config = config

    config = ImplConfig(scale=2.5)
    restored = round_trip(config)
    assert restored.class_name == config.class_name
    assert isinstance(restored.instantiate(Interface), Impl)


def test_pickle_round_trip_is_stable_across_repeats():
    """Repeated round trips must not degrade the config."""
    config = NestedConfig()
    for _ in range(3):
        config = pickle.loads(pickle.dumps(config))
    assert isinstance(config.leaf, LeafConfig)
    assert config == NestedConfig()
