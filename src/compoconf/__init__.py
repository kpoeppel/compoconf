"""
CompoConf: A Compositional Configuration Library

This module provides a framework for managing configurations in a type-safe and composable way.
It allows for the definition of interfaces, their implementations, and corresponding configurations
using Python's dataclass system.
"""

from .compoconf import (  # pylint: disable=W0406
    ConfigInterface,
    RegistrableConfigInterface,
    Registry,
    register,
    register_interface,
)
from .nonstrict_dataclass import NonStrictDataclass, asdict
from .parsing import dump_config, parse_config
from .util import (
    ConfigError,
    LiteralError,
    MissingValue,
    assert_check_literals,
    assert_check_nonmissing,
    from_annotations,
    make_dataclass_picklable,
    partial_call,
    validate_literal_field,
)

__version__ = "0.1.0"

__all__ = [
    "NonStrictDataclass",
    "asdict",
    "RegistrableConfigInterface",
    "ConfigInterface",
    "Registry",
    "register",
    "register_interface",
    "parse_config",
    "dump_config",
    "partial_call",
    "from_annotations",
    "make_dataclass_picklable",
    "assert_check_literals",
    "assert_check_nonmissing",
    "validate_literal_field",
    "ConfigError",
    "LiteralError",
    "MissingValue",
]
