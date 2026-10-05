"""Shared sample config types for the round-trip and schema-agreement suites.

Not a test module. These live here rather than being duplicated per suite, and rather than becoming
fixtures, because both suites need them at *import* time to build their ``parametrize`` tables.

:func:`register_mixer` is the exception: it mutates the global registry, so it must run per test
alongside the ``reset_registry`` fixture rather than at import time.
"""

from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface


class Color(Enum):
    """Sample enum: members whose values differ from their names, so by-name and by-value differ."""

    RED = "red"
    BLUE = "blue"


@dataclass
class Leaf:
    """Sample config with nothing but defaulted scalars."""

    a: int = 1
    b: str = "x"


def register_mixer():
    """Register an interface with two implementations and return the pieces a test needs.

    Call from a fixture that also requests ``reset_registry``, so each test gets a clean registry.

    Returns:
        A namespace with ``interface``, ``attn_config`` and ``conv_config``.
    """

    @register_interface
    class Mixer(RegistrableConfigInterface):
        """The interface whose ``cfgtype`` union the tests annotate fields with."""

    @dataclass
    class AttnConfig(ConfigInterface):
        """Config of the first implementation."""

        heads: int = 8

    @register
    class Attn(Mixer):  # pylint: disable=W0612
        """First implementation."""

        config: AttnConfig

    @dataclass
    class ConvConfig(ConfigInterface):
        """Config of the second implementation, with a disjoint field set."""

        kernel: int = 3

    @register
    class Conv(Mixer):  # pylint: disable=W0612
        """Second implementation."""

        config: ConvConfig

    return SimpleNamespace(interface=Mixer, attn_config=AttnConfig, conv_config=ConvConfig)
