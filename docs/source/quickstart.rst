Quick Start Guide
=================

This guide will help you get started with CompoConf by walking through common use cases and patterns.

Basic Usage
-----------

1. First, define an interface that your configurable classes will implement:

.. code-block:: python

    from dataclasses import dataclass
    from compoconf import (
        RegistrableConfigInterface,
        ConfigInterface,
        register_interface,
        register,
    )

    @register_interface
    class ModelInterface(RegistrableConfigInterface):
        pass

2. Create a configuration class for your implementation:

.. code-block:: python

    @dataclass
    class MLPConfig(ConfigInterface):
        hidden_size: int = 128
        num_layers: int = 2
        activation: str = "relu"

3. Create and register your implementation:

.. code-block:: python

    @register
    class MLPModel(ModelInterface):
        config_class = MLPConfig

        def __init__(self, config):
            self.config = config
            self.hidden_size = config.hidden_size
            self.num_layers = config.num_layers
            self.activation = config.activation

4. Use your configured class:

.. code-block:: python

    # Create configuration
    config = MLPConfig(hidden_size=256)

    # Instantiate the model
    model = config.instantiate(ModelInterface)

Nested Configurations
---------------------

CompoConf excels at handling nested configurations:

.. code-block:: python

    @dataclass
    class OptimizerConfig(ConfigInterface):
        learning_rate: float = 0.001
        weight_decay: float = 0.0

    @dataclass
    class TrainerConfig(ConfigInterface):
        model: ModelInterface.cfgtype
        optimizer: OptimizerConfig
        max_epochs: int = 100

    # Parse from dictionary
    config_dict = {
        "model": {
            "class_name": "MLPModel",
            "hidden_size": 512,
            "num_layers": 3
        },
        "optimizer": {
            "learning_rate": 0.01
        },
        "max_epochs": 200
    }

    trainer_config = parse_config(TrainerConfig, config_dict)

Using with OmegaConf
--------------------

CompoConf integrates with OmegaConf for enhanced configuration handling:

.. code-block:: python

    from omegaconf import OmegaConf

    # Load from YAML
    conf = OmegaConf.load('config.yaml')

    # Parse into typed configuration
    config = parse_config(TrainerConfig, conf)

Type Safety
-----------

CompoConf provides comprehensive type checking:

.. code-block:: python

    # This will raise a TypeError - wrong type for hidden_size
    bad_config = MLPConfig(hidden_size="not a number")

    # This will raise a ValueError - unknown configuration key
    parse_config(MLPConfig, {"hidden_size": 128, "unknown_param": "value"}, strict=True)

Multiple Implementations
------------------------

You can register multiple implementations for the same interface:

.. code-block:: python

    @dataclass
    class CNNConfig(ConfigInterface):
        channels: list[int] = field(default_factory=lambda: [64, 128, 256])
        kernel_size: int = 3

    @register
    class CNNModel(ModelInterface):
        config_class = CNNConfig

    # Both implementations can be instantiated from the same interface
    mlp = MLPConfig().instantiate(ModelInterface)
    cnn = CNNConfig().instantiate(ModelInterface)

Best Practices
--------------

1. Always inherit configurations from ConfigInterface
2. Use type annotations for all configuration fields
3. Provide sensible defaults when possible
4. Use strict mode with parse_config to catch typos
5. Keep configurations close to their implementations
6. Use nested configurations to organize complex systems
