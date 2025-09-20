API Reference
=============

Core Components
---------------

RegistrableConfigInterface
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: compoconf.RegistrableConfigInterface
   :members:
   :special-members: __init__
   :show-inheritance:

ConfigInterface
~~~~~~~~~~~~~~~

.. autoclass:: compoconf.ConfigInterface
   :members:
   :special-members: __init__
   :show-inheritance:

Registry System
---------------

Registry
~~~~~~~~

.. autodata:: compoconf.Registry
   :annotation: = The global registry singleton

.. autoclass:: compoconf._RegistrySingleton
   :members:
   :private-members:
   :special-members: __init__, __str__
   :show-inheritance:

Decorators
----------

.. autofunction:: compoconf.register

.. autofunction:: compoconf.register_interface

Configuration Parsing
---------------------

.. autofunction:: compoconf.parse_config


Type Variables
--------------

.. py:data:: compoconf.RegistrableConfigInterface.cfgtype

   A TypeVar representing the configuration type for a registrable interface.
   This is dynamically created based on the registered implementations of the interface.

   Example:

   .. code-block:: python

       @dataclass
       class TrainerConfig:
           model: ModelInterface.cfgtype  # References all possible model configurations


Utilities
---------

.. autofunction:: compoconf.from_annotations

.. autofunction:: compoconf.partial_call

.. autofunction:: compoconf.make_dataclass_picklable

.. autofunction:: compoconf.validate_literal_field

.. autofunction:: compoconf.assert_check_literals

.. autofunction:: compoconf.assert_check_nonmissing
