# CompoConf

CompoConf is a Python library for compositional configuration management. It provides a type-safe way to define, parse, and instantiate configurations for complex, modular systems.

## Features

- Type-safe configuration parsing with dataclass support
- Registry-based class instantiation
- Inheritance-based interface registration
- Support for nested configurations
- Optional OmegaConf integration
- Strict type checking and validation

## Installation

```bash
pip install compoconf
```

## Quick Start

Here's a simple example of how to use CompoConf:

```python
from dataclasses import dataclass
from compoconf import (
    RegistrableConfigInterface,
    ConfigInterface,
    register_interface,
    register,
)

# Define an interface
@register_interface
class ModelInterface(RegistrableConfigInterface):
    pass

# Define a configuration
@dataclass
class MLPConfig(ConfigInterface):
    hidden_size: int = 128
    num_layers: int = 2

# Register a class with its configuration
@register
class MLPModel(ModelInterface):
    config_class = MLPConfig

    def __init__(self, config):
        self.config = config
        # Initialize model with config...

# Create and use configurations
config = MLPConfig(hidden_size=256)
model = config.instantiate(ModelInterface)
```

## Advanced Usage

### Nested Configurations

CompoConf supports nested configurations through type annotations:

```python
@dataclass
class TrainerConfig(ConfigInterface):
    model: ModelInterface.cfgtype  # References the interface type
    learning_rate: float = 0.001

# Parse nested configuration
config = {
    "model": {
        "class_name": "MLPModel",
        "hidden_size": 256
    },
    "learning_rate": 0.01
}

trainer_config = parse_config(TrainerConfig, config)
```

### Type Safety

The library provides comprehensive type checking:
- Validates configuration values against their type annotations
- Ensures registered classes match their interfaces
- Checks for missing required fields
- Supports strict mode for catching unknown configuration keys

### OmegaConf Integration

CompoConf optionally integrates with OmegaConf for enhanced configuration handling:

```python
from omegaconf import OmegaConf

# Load configuration from YAML
conf = OmegaConf.load('config.yaml')
config = parse_config(ModelConfig, conf)
```

### Registry System

The registry system allows for dynamic class instantiation based on configuration:

```python
# Register multiple implementations
@dataclass
class CNNConfig(ConfigInterface):
    kernel_size: int = 4

@register
class CNNModel(ModelInterface):
    config_class = CNNConfig

@dataclass
class TransformerConfig(ConfigInterface):
    hidden_size: int = 128
    num_heads: int = 4

@register
class TransformerModel(ModelInterface):
    config_class = TransformerConfig

# Configuration automatically creates correct instance
config = {
    "model": {
        "class_name": "TransformerModel",
        "num_heads": 8,
        "hidden_size": 512
    }
}
```

## API Reference

### Core Classes

- `RegistrableConfigInterface`: Base class for interfaces that can be configured
- `ConfigInterface`: Base class for configuration dataclasses
- `Registry`: Singleton managing registration of interfaces and implementations
- `NonStrictDataclass`: Base class for dataclasses that accept extra (undeclared) keyword arguments
- `FrozenNonStrictDataclass`: Immutable (hashable) counterpart of `NonStrictDataclass`

### Decorators

- `@register_interface`: Register a new interface
- `@register`: Register an implementation class

### Functions

- `parse_config(config_class, data, strict=True)`: Parse configuration data into typed objects
- `dump_config(obj)`: Convert a config (tree of dataclasses) into a pure Python structure (JSON/YAML-ready)
- `asdict(obj)`: Convert a dataclass (including `NonStrictDataclass`, with extras flattened) to a dictionary

## Enhanced Functionality

### Parsing Module

The parsing module has been enhanced to provide more robust and flexible configuration parsing capabilities. Key improvements include:

-   Improved handling of nested configurations and unions.
-   Enhanced type validation and error reporting.
-   Support for parsing configurations from various data sources (e.g., JSON, YAML).

### Non-Strict Dataclasses

`NonStrictDataclass` is a dataclass base that may be extended at runtime with extra
keyword arguments beyond its declared fields. Inheriting classes must use
`@dataclass(init=False)` so the custom initializer is preserved:

```python
from dataclasses import dataclass, replace
from compoconf import NonStrictDataclass, asdict

@dataclass(init=False)
class MyConfig(NonStrictDataclass):
    a: int
    b: str = "default_b"

cfg = MyConfig(a=1, c="extra", d=3.14)   # c, d are "extras"
cfg.c                                     # -> "extra"
asdict(cfg)                               # -> {"a": 1, "b": "default_b", "c": "extra", "d": 3.14}
replace(cfg, a=2)                         # extras are preserved across dataclasses.replace
```

It works with the standard `dataclasses` helpers (`replace`, `asdict`, `astuple`,
`fields`), as well as `copy`/`deepcopy` and `pickle`.

**Extras are untyped.** Extra attributes are stored as-is and are never type-checked or
re-typed on parsing. Because of this, **extras must be plain data** (scalars, and
arbitrarily nested `dict`/`list`/`tuple` of plain data). Storing a dataclass/config as an
*extra* is **not supported** — it cannot be serialized or round-tripped through the parser,
since there is no type information to reconstruct it.

If you need a nested, typed config that round-trips, declare it as a real field instead of
relying on extras. Make it optional by giving it a `Type | None = None` annotation so it is
an explicit, parseable option:

```python
@dataclass(init=False)
class Parent(NonStrictDataclass):
    name: str = "p"
    child: MyConfig | None = None        # typed, optional, round-trips through parse_config
```

For an immutable variant, inherit from `FrozenNonStrictDataclass` and decorate subclasses
with `@dataclass(init=False, frozen=True)`. Frozen instances are read-only (declared fields
*and* extras) and hashable. Note that a frozen non-strict dataclass must inherit from
`FrozenNonStrictDataclass` — Python forbids a frozen dataclass inheriting from the
non-frozen `NonStrictDataclass`.

### Util Module

The util module now includes powerful utilities for dynamic configuration and validation:

-   `partial_call`: Enables the creation of configurable classes from functions, allowing for dynamic modification of function arguments through configuration.
-   `from_annotations`: Simplifies the creation of configurable classes by automatically extracting configuration parameters from class annotations.
-   `validate_literal_field` and `assert_check_literals`: Provide mechanisms for validating Literal type annotations in dataclasses, ensuring that configuration values are within the allowed set of options.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Author

Korbinian Pöppel (korbip@korbip.de)
