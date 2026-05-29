"""conftest for compoconf"""

try:
    import pytest

    from compoconf.compoconf import Registry

    @pytest.fixture
    def reset_registry():
        """Reset the registry before each test."""
        for reg in list(Registry._registries):  # pylint: disable=W0212
            Registry._registries.pop(reg)  # pylint: disable=W0212
        for reg in list(Registry._registry_classes):  # pylint: disable=W0212
            Registry._registry_classes.pop(reg)  # pylint: disable=W0212
        yield

except ImportError:
    pass
