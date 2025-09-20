Development Guide
=================

This guide covers everything you need to know to develop CompoConf, including setting up your development environment, running tests, and building documentation.

Development Installation
------------------------

1. Clone the repository:

.. code-block:: bash

    git clone git@github.com:kpoeppel/compoconf.git
    cd compoconf

2. Install development dependencies:

.. code-block:: bash

    pip install -e ".[dev,test,docs]"

This will install:

- Development tools (black, isort, flake8, mypy)
- Testing tools (pytest, pytest-cov, pytest-sugar)
- Documentation tools (sphinx and extensions)

Running Tests
-------------

CompoConf uses pytest for testing. To run the tests:

.. code-block:: bash

    pytest

To run tests with coverage report:

.. code-block:: bash

    pytest --cov=compoconf --cov-report=term-missing

Code Style
----------

CompoConf follows standard Python code style guidelines:

- Black for code formatting
- isort for import sorting
- flake8 for style guide enforcement
- mypy for static type checking

To format code:

.. code-block:: bash

    black src tests
    isort src tests

To check code:

.. code-block:: bash

    flake8 src tests
    mypy src tests

Building Documentation
----------------------

The documentation is built using Sphinx. To build:

.. code-block:: bash

    cd docs
    make html

The built documentation will be in ``docs/build/html``.

To serve the documentation locally:

.. code-block:: bash

    python -m http.server -d build/html 8000

Then visit http://localhost:8000 in your browser.

Making Changes
--------------

1. Create a new branch for your changes:

.. code-block:: bash

    git checkout -b feature-name

2. Make your changes
3. Run tests and style checks:

.. code-block:: bash

    pytest
    black src tests
    isort src tests
    flake8 src tests
    mypy src tests

4. Update documentation if needed
5. Submit a pull request

Project Structure
-----------------

::

    compoconf/
    ├── src/
    │   └── compoconf/
    │       ├── __init__.py
    │       └── compoconf.py
    ├── tests/
    │   └── test_compoconf.py
    ├── docs/
    │   └── source/
    │       ├── conf.py
    │       ├── index.rst
    │       └── ...
    ├── pyproject.toml
    └── README.md

Release Process
---------------

1. Update version in:
   - src/compoconf/__init__.py
   - pyproject.toml
   - docs/source/conf.py

2. Update CHANGELOG.md

3. Create a release commit:

.. code-block:: bash

    git commit -m "Release vX.Y.Z"
    git tag vX.Y.Z
    git push origin main --tags

4. Build and upload to PyPI:

.. code-block:: bash

    python -m build
    python -m twine upload dist/*
