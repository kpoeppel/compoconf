"""
Tests for registry introspection, actionable (loud) registry errors, and the
``compoconf.load`` discovery helper.

These cover the "explicit/visible workflow" features layered on top of the implicit,
import-driven registration: ``compoconf.registered`` / ``Registry.implementations`` for
introspection, clear errors from ``Registry.get_class`` when something is not registered,
and ``compoconf.load`` for importing a module/package and reporting what it registered.
"""

# Fixtures used as test arguments and decorator-registered helper classes are inherent to the
# registry pattern; silence the resulting pytest/registry lint noise for this module.
# pylint: disable=redefined-outer-name,unused-variable,unused-argument

import importlib
import sys
import textwrap
from dataclasses import dataclass

import pytest  # pylint: disable=E0401

# Import from the submodule (like the other test modules) so type-checking resolves against the
# in-repo package rather than any stale installed copy.
from compoconf.compoconf import (
    ConfigInterface,
    RegistrableConfigInterface,
    Registry,
    load,
    register,
    register_interface,
    registered,
)


@pytest.fixture
def model_registry(reset_registry):  # pylint: disable=unused-argument
    """A fresh registry with one interface (``ModelInterface``) and two implementations."""

    @register_interface
    class ModelInterface(RegistrableConfigInterface):
        """Interface fixture."""

    @dataclass
    class MLPConfig(ConfigInterface):
        """MLP config."""

        h: int = 8

    @register
    class MLP(ModelInterface):
        """MLP implementation."""

        config_class = MLPConfig

    @dataclass
    class CNNConfig(ConfigInterface):
        """CNN config."""

        k: int = 3

    @register
    class CNN(ModelInterface):
        """CNN implementation."""

        config_class = CNNConfig

    return ModelInterface


# --------------------------------------------------------------------------- #
# Introspection                                                                #
# --------------------------------------------------------------------------- #
def test_registered_lists_implementation_names(model_registry):
    """``registered(interface)`` returns the sorted implementation names."""
    assert registered(model_registry) == ["CNN", "MLP"]


def test_registered_all_returns_interface_mapping(model_registry):
    """``registered()`` returns a ``{interface_cls: [names]}`` mapping."""
    mapping = registered()
    assert {k.__name__: v for k, v in mapping.items()} == {"ModelInterface": ["CNN", "MLP"]}


def test_registered_unknown_interface_raises(reset_registry):  # pylint: disable=unused-argument
    """Asking for an interface that has no registry raises ``KeyError``."""

    class Unregistered(RegistrableConfigInterface):
        """Never decorated with @register_interface."""

    with pytest.raises(KeyError):
        registered(Unregistered)


def test_implementations_dedupes_across_interfaces(reset_registry):  # pylint: disable=unused-argument
    """A class registered under several interfaces appears once in ``implementations``."""

    @register_interface
    class Base(RegistrableConfigInterface):
        """Base interface."""

    @register_interface
    class Derived(Base):
        """Derived interface; impls register under both Base and Derived."""

    @dataclass
    class ImplConfig(ConfigInterface):
        """Impl config."""

    @register
    class Impl(Derived):
        """Registered under both Base and Derived."""

        config_class = ImplConfig

    names = [c.__name__ for c in Registry.implementations()]
    assert names.count("Impl") == 1


# --------------------------------------------------------------------------- #
# Actionable (loud) errors                                                     #
# --------------------------------------------------------------------------- #
def test_get_class_missing_name_error_is_actionable(model_registry):
    """A missing implementation name yields an error listing options and an import hint."""
    with pytest.raises(KeyError) as exc:
        Registry.get_class(model_registry, "DoesNotExist")
    msg = str(exc.value)
    assert "DoesNotExist" in msg
    assert "MLP" in msg and "CNN" in msg  # lists the registered options
    assert "compoconf.load" in msg  # actionable hint


def test_get_class_no_registry_error_is_actionable(reset_registry):  # pylint: disable=unused-argument
    """Looking up against a non-registry interface hints at @register_interface."""

    class NoReg(RegistrableConfigInterface):
        """Never registered as an interface."""

    with pytest.raises(KeyError) as exc:
        Registry.get_class(NoReg, "X")
    assert "register_interface" in str(exc.value)


# --------------------------------------------------------------------------- #
# compoconf.load discovery                                                     #
# --------------------------------------------------------------------------- #
_PKG_NAME = "cc_load_fixture_pkg"


def _write_plugin_pkg(root, name):
    """Create a small package with two submodules, each registering an implementation."""
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")  # the package itself registers nothing
    (pkg / "models.py").write_text(
        textwrap.dedent(
            """
            from dataclasses import dataclass
            from compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface

            @register_interface
            class PluginInterface(RegistrableConfigInterface):
                pass

            @dataclass
            class AlphaConfig(ConfigInterface):
                x: int = 1

            @register
            class Alpha(PluginInterface):
                config_class = AlphaConfig
                def __init__(self, config):
                    self.config = config
            """
        )
    )
    (pkg / "more.py").write_text(
        textwrap.dedent(
            f"""
            from dataclasses import dataclass
            from compoconf import ConfigInterface, register
            from {name}.models import PluginInterface

            @dataclass
            class BetaConfig(ConfigInterface):
                y: int = 2

            @register
            class Beta(PluginInterface):
                config_class = BetaConfig
                def __init__(self, config):
                    self.config = config
            """
        )
    )
    return pkg


@pytest.fixture
def plugin_pkg(tmp_path, monkeypatch, reset_registry):  # pylint: disable=unused-argument
    """Build an importable plugin package on a temp path and clean it from sys.modules."""

    def _purge():
        for mod in [m for m in list(sys.modules) if m == _PKG_NAME or m.startswith(_PKG_NAME + ".")]:
            del sys.modules[mod]

    _write_plugin_pkg(tmp_path, _PKG_NAME)
    monkeypatch.syspath_prepend(str(tmp_path))
    _purge()
    yield _PKG_NAME
    _purge()


def test_load_recurse_imports_submodules_and_reports(plugin_pkg):  # pylint: disable=redefined-outer-name
    """``load(pkg, recurse=True)`` imports every submodule and returns what registered."""
    out = load(plugin_pkg, recurse=True)
    assert sorted(c.__name__ for c in out) == ["Alpha", "Beta"]
    iface = next(k for k in registered() if k.__name__ == "PluginInterface")
    assert registered(iface) == ["Alpha", "Beta"]


def test_load_recurse_false_skips_submodules(plugin_pkg):  # pylint: disable=redefined-outer-name
    """``recurse=False`` imports only the package __init__, which registers nothing here."""
    assert load(plugin_pkg, recurse=False) == []


def test_load_second_call_returns_empty(plugin_pkg):  # pylint: disable=redefined-outer-name
    """A second load is a no-op (already imported) and reports nothing new."""
    load(plugin_pkg, recurse=True)
    assert load(plugin_pkg, recurse=True) == []


def test_load_accepts_module_object(plugin_pkg):  # pylint: disable=redefined-outer-name
    """``load`` accepts an already-imported module object and can still recurse into it."""
    pkg_mod = importlib.import_module(plugin_pkg)  # __init__ only: registers nothing yet
    out = load(pkg_mod, recurse=True)
    assert sorted(c.__name__ for c in out) == ["Alpha", "Beta"]
