Installation Guide
==================

CompoConf can be installed in several ways depending on your needs.

Basic Installation
------------------

The simplest way to install CompoConf is via pip:

.. code-block:: bash

    pip install compoconf

This will install the core package with minimal dependencies.

Development Installation
------------------------

For development, you'll want to install additional dependencies for testing, documentation, and development tools:

.. code-block:: bash

    pip install "compoconf[dev,test,docs]"

Or from source:

.. code-block:: bash

    git clone ssh://git@git.bioinf.jku.at:5792/poeppel/compoconf.git
    cd compoconf
    pip install -e ".[dev,test,docs]"

Optional Dependencies
---------------------

OmegaConf Integration
~~~~~~~~~~~~~~~~~~~~~

To use CompoConf with OmegaConf for enhanced configuration handling:

.. code-block:: bash

    pip install "compoconf[omegaconf]"

All Extras
~~~~~~~~~~

To install all optional dependencies:

.. code-block:: bash

    pip install "compoconf[dev,test,docs,omegaconf]"

Requirements
------------

CompoConf requires:

- Python >= 3.7
- typing-extensions >= 4.0.0
- dataclasses (for Python < 3.7)

Optional requirements:

- omegaconf >= 2.0.0 (for OmegaConf integration)
- pytest >= 7.0.0 (for testing)
- pytest-cov >= 4.0.0 (for coverage reports)
- sphinx >= 7.0.0 (for documentation)
- black >= 23.0.0 (for code formatting)
- isort >= 5.12.0 (for import sorting)
- flake8 >= 6.0.0 (for style checking)
- mypy >= 1.5.0 (for type checking)

Verifying Installation
----------------------

After installation, you can verify it works by running Python and importing the package:

.. code-block:: python

    >>> import compoconf
    >>> compoconf.__version__
    '0.1.0'

You can also run the tests if you installed the test dependencies:

.. code-block:: bash

    pytest --pyargs compoconf

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

1. ImportError: No module named 'compoconf'

   - Make sure you've installed the package: ``pip list | grep compoconf``
   - Check your Python environment: ``which python``
   - Verify PYTHONPATH if installing in development mode

2. Missing dependencies

   - Install with the required extra: ``pip install "compoconf[extra_name]"``
   - Check installed packages: ``pip freeze``

Getting Help
~~~~~~~~~~~~

If you encounter any issues:

1. Check the :doc:`development` guide for common development issues
2. Search existing GitHub issues
3. Create a new issue with:
   - Your Python version
   - Installation method used
   - Complete error message
   - Minimal example reproducing the issue
