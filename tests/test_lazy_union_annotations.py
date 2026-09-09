"""The ``cfgtype`` proxies must be usable as type annotations on every
supported Python.

Python 3.10's ``typing._type_check`` ends with::

    if not callable(arg):
        raise TypeError(f"{msg} Got {arg!r:.100}.")

so an annotation object that is neither a class nor callable is rejected with
"Forward references must evaluate to types". That took down every
``Interface.cfgtype`` annotation on 3.10. Python 3.11 relaxed the check to
reject only a raw tuple, which is why the breakage looked version-specific
rather than like a plain bug.
"""

from dataclasses import dataclass

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, Registry, register, register_interface


# pylint: disable=C0115,C0116,W0212,W0621,W0613,C0415,W0612,W0231,E1120
@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry before each test."""
    for reg in list(Registry._registries):
        Registry._registries.pop(reg)
    yield


class TestLazyProxiesAreValidAnnotations:
    """The cfgtype proxies must survive typing's annotation checks.

    Python 3.10's ``typing._type_check`` ends with ``if not callable(arg):
    raise TypeError``, so a proxy that is neither a class nor callable is
    rejected with "Forward references must evaluate to types" -- which took down
    every ``Interface.cfgtype`` annotation on 3.10. Python 3.11 relaxed that
    check to reject only a raw tuple, which is why this was invisible there.
    """

    def test_proxies_pass_typing_type_check(self):
        import typing

        @register_interface
        class Iface(RegistrableConfigInterface):
            """Interface whose cfgtype proxy is under test."""

        @dataclass
        class ImplConfig(ConfigInterface):
            """Config for the registered implementation."""

            class_name: str = "Impl"

        @register
        class Impl(Iface):
            """Registered so the proxy resolves to a non-empty union."""

            config: ImplConfig

            def __init__(self, config):
                self.config = config

        assert Impl is not None

        # Both the bare proxy and the `| None` form are used as annotations.
        for annotation in (Iface.cfgtype, Iface.cfgtype | None):
            assert callable(annotation), f"{annotation!r} must be callable for 3.10's _type_check"
            # _type_check is what raised; it must now return the annotation.
            assert typing._type_check(annotation, "msg") is annotation

    def test_resolving_annotations_works(self):
        """get_type_hints is the path that actually invoked _type_check."""
        from typing import get_type_hints

        @register_interface
        class Iface2(RegistrableConfigInterface):
            """Interface whose cfgtype proxy is under test."""

        @dataclass
        class Impl2Config(ConfigInterface):
            """Config for the registered implementation."""

            class_name: str = "Impl2"

        @register
        class Impl2(Iface2):
            """Registered so the proxy resolves to a non-empty union."""

            config: Impl2Config

            def __init__(self, config):
                self.config = config

        assert Impl2 is not None

        @dataclass(kw_only=True)
        class Holder(ConfigInterface):
            """Holds a cfgtype-annotated field, the shape that failed on 3.10."""

            thing: Iface2.cfgtype | None = None  # pylint: disable=E1120

        hints = get_type_hints(Holder)  # raised TypeError on 3.10 before the fix
        assert "thing" in hints

    def test_calling_a_proxy_is_a_clear_error(self):
        """Callable purely to satisfy typing; a union has no one constructor."""

        @register_interface
        class Iface3(RegistrableConfigInterface):
            """Interface whose cfgtype proxy is under test."""

        with pytest.raises(TypeError, match="is a type annotation, not a constructor"):
            Iface3.cfgtype()
        with pytest.raises(TypeError, match="is a type annotation, not a constructor"):
            (Iface3.cfgtype | None)()
