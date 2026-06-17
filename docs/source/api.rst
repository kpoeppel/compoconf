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

Configuration Parsing and Serialization
---------------------------------------

.. autofunction:: compoconf.parse_config

.. autofunction:: compoconf.parse_file

.. autofunction:: compoconf.dump_config

.. autofunction:: compoconf.asdict


Registry Discovery and Introspection
------------------------------------

.. autofunction:: compoconf.load

.. autofunction:: compoconf.registered


Non-Strict Dataclasses
----------------------

.. autoclass:: compoconf.NonStrictDataclass
   :members:
   :show-inheritance:

.. autoclass:: compoconf.FrozenNonStrictDataclass
   :members:
   :show-inheritance:


Type Variables
--------------

.. py:data:: compoconf.RegistrableConfigInterface.cfgtype

   A lazy proxy (:class:`compoconf.LazyConfigUnion`) representing the union of all configuration
   types registered under a registrable interface. Resolution of the registered implementations is
   deferred until parse time, so it is safe to use as a field annotation even before all
   implementations have been imported and registered.

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
