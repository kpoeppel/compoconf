"""Tests for registry conflicts that are easy to create by accident.

In their own module rather than appended to test_compoconf.py, which is at the 1000-line pylint
limit.
"""

from dataclasses import dataclass

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, Registry, register, register_interface

# pylint: disable=C0115,C0116,W0212,W0621,W0613


def test_warns_when_two_implementations_share_a_config_class(reset_registry, caplog):
    """The second registration takes the config class over, leaving the first unreachable from it."""

    @register_interface
    class SharedInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class SharedConfig(ConfigInterface):
        value: int = 1

    @register
    class ImplA(SharedInterface):  # pylint: disable=W0612
        config_class = SharedConfig

    caplog.clear()
    with caplog.at_level("WARNING"):

        @register
        class ImplB(SharedInterface):
            config_class = SharedConfig

    assert "is already the config class of" in caplog.text
    assert "ImplA" in caplog.text and "ImplB" in caplog.text
    # and the warning is telling the truth: ImplA is no longer reachable from SharedConfig
    assert SharedConfig.class_name == "ImplB"
    assert isinstance(SharedConfig().instantiate(SharedInterface), ImplB)


def test_registering_under_several_interfaces_does_not_warn(reset_registry, caplog):
    """One class entering several registries via its MRO is normal, not a conflict."""

    @register_interface
    class Outer(RegistrableConfigInterface):
        pass

    @register_interface
    class Inner(Outer):
        pass

    @dataclass
    class OnlyConfig(ConfigInterface):
        value: int = 1

    caplog.clear()
    with caplog.at_level("WARNING"):

        @register
        class OnlyImpl(Inner):  # pylint: disable=W0612
            config_class = OnlyConfig

    assert "is already the config class of" not in caplog.text
    assert Registry.registered(Outer) == ["OnlyImpl"]
    assert Registry.registered(Inner) == ["OnlyImpl"]


def test_inherited_class_name_without_a_live_owner_stays_informational(reset_registry, caplog):
    """A config class carrying a name it was never registered under is not a conflict."""

    @register_interface
    class Iface(RegistrableConfigInterface):
        pass

    @dataclass
    class BaseConfig(ConfigInterface):
        value: int = 1

    # as the util decorators do: a config class arrives already carrying a class_name, but nothing
    # is registered under that name
    BaseConfig.class_name = "NeverRegistered"

    caplog.clear()
    with caplog.at_level("WARNING"):

        @register
        class Impl(Iface):  # pylint: disable=W0612
            config_class = BaseConfig

    assert "is already the config class of" not in caplog.text
    assert BaseConfig.class_name == "Impl"


@pytest.mark.parametrize("value", ["", None, 0])
def test_absent_previous_class_name_is_not_a_conflict(reset_registry, caplog, value):
    @register_interface
    class Iface(RegistrableConfigInterface):
        pass

    @dataclass
    class Cfg(ConfigInterface):
        value: int = 1

    Cfg.class_name = value
    caplog.clear()
    with caplog.at_level("WARNING"):

        @register
        class Impl(Iface):  # pylint: disable=W0612
            config_class = Cfg

    assert caplog.text == ""
    assert Cfg.class_name == "Impl"


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
