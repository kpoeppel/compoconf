Advanced Usage Guide
====================

This guide focuses on CompoConf's core strength: composability in configuration management.

Composing Configurations
------------------------

The real power of CompoConf lies in its ability to compose configurations in a type-safe way:

.. code-block:: python

    from dataclasses import dataclass
    from compoconf import RegistrableConfigInterface, ConfigInterface, register_interface, register

    # Define interfaces for different components
    @register_interface
    class DatasetInterface(RegistrableConfigInterface):
        pass

    @register_interface
    class ModelInterface(RegistrableConfigInterface):
        pass

    # Define component configurations
    @dataclass
    class CSVDatasetConfig(ConfigInterface):
        path: str
        batch_size: int = 32
        shuffle: bool = True

    @dataclass
    class MLPConfig(ConfigInterface):
        hidden_size: int = 128
        num_layers: int = 2

    # Register implementations
    @register
    class CSVDataset(DatasetInterface):
        config_class = CSVDatasetConfig

        def __init__(self, config):
            self.config = config
            # Initialize dataset with config parameters

    @register
    class MLPModel(ModelInterface):
        config_class = MLPConfig

        def __init__(self, config):
            self.config = config
            # Initialize model with config parameters

Composing with a Trainer
------------------------

A Trainer can compose and manage these components:

.. code-block:: python

    @register_interface
    class TrainerInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TrainerConfig(ConfigInterface):
        dataset: DatasetInterface.cfgtype
        model: ModelInterface.cfgtype
        num_epochs: int = 100
        learning_rate: float = 0.001

    @register
    class Trainer(TrainerInterface):
        config_class = TrainerConfig

        def __init__(self, config):
            self.config = config
            # Instantiate components using their configs
            self.dataset = config.dataset.instantiate(DatasetInterface)
            self.model = config.model.instantiate(ModelInterface)
            self.num_epochs = config.num_epochs
            self.learning_rate = config.learning_rate

        def train(self):
            # Training logic using self.dataset and self.model
            pass

    # Use with direct instantiation
    config = TrainerConfig(
        dataset=CSVDatasetConfig(path="data.csv"),
        model=MLPConfig(hidden_size=256)
    )
    trainer = config.instantiate(TrainerInterface)

    # Or parse from dictionary
    config_dict = {
        "dataset": {
            "class_name": "CSVDataset",
            "path": "data.csv",
            "batch_size": 64
        },
        "model": {
            "class_name": "MLPModel",
            "hidden_size": 512
        },
        "num_epochs": 200,
        "learning_rate": 0.01
    }
    config = parse_config(TrainerConfig, config_dict)
    trainer = config.instantiate(TrainerInterface)

Nested Composition
------------------

Configurations can be nested to any depth while maintaining type safety:

.. code-block:: python

    @dataclass
    class PreprocessConfig(ConfigInterface):
        normalize: bool = True
        augment: bool = False

    @dataclass
    class EnhancedDatasetConfig(ConfigInterface):
        path: str
        preprocess: PreprocessConfig
        cache_size: int = 1000

    @register
    class EnhancedDataset(DatasetInterface):
        config_class = EnhancedDatasetConfig

        def __init__(self, config):
            self.config = config
            self.preprocess = config.preprocess
            # Initialize dataset with preprocessing options

    # Use nested configuration with trainer
    trainer_config = TrainerConfig(
        dataset=EnhancedDatasetConfig(
            path="data.csv",
            preprocess=PreprocessConfig(normalize=True, augment=True)
        ),
        model=MLPConfig(hidden_size=256)
    )
    trainer = trainer_config.instantiate(TrainerInterface)

Best Practices
--------------

1. Keep Configurations Focused
   - Each configuration class should have a single responsibility
   - Use composition to build complex configurations from simple ones

2. Type Safety
   - Always use type annotations for configuration fields
   - Let the type system help catch configuration errors early

3. Default Values
   - Provide sensible defaults when possible
   - Document the meaning and impact of each configuration option

4. Validation
   - Add validation in __post_init__ when needed
   - Keep validation logic close to the configuration definition
