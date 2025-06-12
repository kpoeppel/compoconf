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

### Decorators

- `@register_interface`: Register a new interface
- `@register`: Register an implementation class

### Functions

- `parse_config(config_class, data, strict=True)`: Parse configuration data into typed objects

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Author

Korbinian Pöppel (korbip@korbip.de)
