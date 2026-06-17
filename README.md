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

### Loading config files

`parse_file` reads a JSON or YAML file (format inferred from the extension) and parses it into a
typed config in one call:

```python
from compoconf import parse_file

config = parse_file(ModelConfig, "config.yaml")   # or "config.json"
```

YAML support requires PyYAML (`pip install pyyaml`); JSON works out of the box.

### Strict scalar parsing

By default, scalar values are coerced to the annotated type (e.g. the string `"5"` becomes `5` for
an `int` field, and a float is truncated to an `int`). Pass `strict_types=True` to `parse_config`
(or `parse_file`) to reject mismatched scalars instead of silently converting them — useful for
catching config typos. The only widening allowed is `int` → `float`.

```python
parse_config(MyConfig, {"n": "5"})                     # -> n == 5   (coerced)
parse_config(MyConfig, {"n": "5"}, strict_types=True)  # -> raises ValueError
```

### Enums

`enum.Enum` fields are supported. A value parses from an existing member, a member **name**, or a
member **value**, and serializes back to its value (so configs round-trip and stay JSON/YAML-safe):

```python
from enum import Enum
from dataclasses import dataclass
from compoconf import ConfigInterface, parse_config, dump_config

class Color(Enum):
    RED = "red"
    GREEN = "green"

@dataclass
class StyleConfig(ConfigInterface):
    color: Color = Color.RED

parse_config(StyleConfig, {"color": "RED"})    # by name  -> Color.RED
parse_config(StyleConfig, {"color": "green"})  # by value -> Color.GREEN
dump_config(StyleConfig(color=Color.GREEN))    # -> {"class_name": "", "color": "green"}
```

### JSON Schema export

`to_json_schema` converts a config class (or any supported annotation) into a JSON Schema
(draft 2020-12) document — handy for editor validation/autocomplete and external tooling. The type
mapping mirrors `parse_config`; dataclasses are placed in `$defs` and referenced via `$ref` (so
shared and recursive configs work), and registered configs pin their `class_name` for union
discrimination.

```python
import json
from compoconf import to_json_schema

schema = to_json_schema(ModelConfig, title="ModelConfig")
json.dumps(schema)   # ready for a JSON Schema validator / editor
```

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

#### Discovering and inspecting registrations

Registration happens as a side effect of importing the module that defines a class. If the module
is never imported, the implementation is never registered — which previously surfaced as a confusing
downstream error. CompoConf makes this explicit and debuggable:

```python
import compoconf

# Import a module/package so its @register decorators run; returns what got registered.
compoconf.load("mypackage.models")               # single module
compoconf.load("mypackage", recurse=True)        # whole package (walks submodules)
# -> [<class 'mypackage.models.MLPModel'>, <class 'mypackage.models.CNNModel'>, ...]

# Inspect the current registry.
compoconf.registered()                # {ModelInterface: ["CNNModel", "TransformerModel"], ...}
compoconf.registered(ModelInterface)  # ["CNNModel", "TransformerModel"]
print(Registry)                       # full human-readable dump
```

If a `class_name` is requested that isn't registered, the error now lists the available options and
reminds you to import (or `compoconf.load(...)`) the module that defines it.

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

- `parse_config(config_class, data, strict=True, strict_types=False)`: Parse configuration data into typed objects
- `parse_file(config_class, path, *, strict=True, strict_types=False, file_format=None)`: Load a JSON/YAML file and parse it into a typed config
- `dump_config(obj)`: Convert a config (tree of dataclasses) into a pure Python structure (JSON/YAML-ready)
- `asdict(obj)`: Convert a dataclass (including `NonStrictDataclass`, with extras flattened) to a dictionary
- `to_json_schema(config_class, *, title=None)`: Generate a JSON Schema (draft 2020-12) for a config type
- `load(module, *, recurse=True)`: Import a module/package to run its registrations; returns the classes registered
- `registered(interface=None)`: Introspect the registry (names per interface, or a full mapping)

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

**Limitations and notes:**

- Subclasses must use `@dataclass(init=False)` (or `@dataclass(init=False, frozen=True)` for the
  frozen variant) so the shared custom initializer is inherited rather than regenerated.
- `InitVar` fields are supported: they are forwarded to `__post_init__` (in declaration order) and
  are not stored. On the frozen variant, a `__post_init__` that derives fields must assign via
  `object.__setattr__`, as with any frozen dataclass.
- A frozen non-strict dataclass must inherit from `FrozenNonStrictDataclass`; Python forbids a
  frozen subclass of the non-frozen `NonStrictDataclass`.
- Extras are untyped plain data only (scalars / nested `dict`/`list`/`tuple`); see above.

### Util Module

The util module includes utilities for dynamic configuration and validation:

-   `partial_call`: Turn a plain function into a registered, config-driven implementation of an
    interface — the config supplies the function's arguments. See the API docs for the full
    signature and an example.
-   `from_annotations`: Build and register a config-driven implementation from an existing class,
    deriving the configuration fields from that class's constructor annotations. See the API docs.
-   `validate_literal_field` / `assert_check_literals`: Validate that `Literal`-typed fields hold an
    allowed value.

```python
from dataclasses import dataclass
from typing import Literal

from compoconf import ConfigInterface, assert_check_literals, validate_literal_field

@dataclass
class OptimizerConfig(ConfigInterface):
    mode: Literal["adam", "sgd"] = "adam"

cfg = OptimizerConfig(mode="adam")
validate_literal_field(cfg, "mode")   # -> True
assert_check_literals(cfg)            # raises compoconf.LiteralError if any Literal field is invalid
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Author

Korbinian Pöppel (korbip@korbip.de)
