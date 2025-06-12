Welcome to CompoConf's documentation!
=====================================

CompoConf is a Python library for compositional configuration management. It provides a type-safe way to define, parse, and instantiate configurations for complex, modular systems.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   quickstart
   api
   advanced
   development

Features
--------

- Type-safe configuration parsing with dataclass support
- Registry-based class instantiation
- Inheritance-based interface registration
- Support for nested configurations
- Optional OmegaConf integration
- Strict type checking and validation

Quick Example
-------------

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

    @dataclass
    class MLPConfig(ConfigInterface):
        hidden_size: int = 128
        num_layers: int = 2

    @register
    class MLPModel(ModelInterface):
        config_class = MLPConfig

        def __init__(self, config):
            self.config = config

    # Create and use configurations
    config = MLPConfig(hidden_size=256)
    model = config.instantiate(ModelInterface)

Installation
------------

You can install CompoConf using pip:

.. code-block:: bash

   pip install compoconf

For development installation with all extras:

.. code-block:: bash

   pip install -e ".[dev,test,docs]"

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
