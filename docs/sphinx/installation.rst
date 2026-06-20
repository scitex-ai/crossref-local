Installation
============

Requirements
------------

- Python 3.10+
- SQLite with FTS5 support (included in most Python installations)

Install from PyPI
-----------------

.. code-block:: bash

    pip install crossref-local

Install with optional dependencies:

.. code-block:: bash

    # With API server support
    pip install crossref-local[api]

    # With MCP server support
    pip install crossref-local[mcp]

    # With visualization support
    pip install crossref-local[viz]

    # All optional dependencies
    pip install crossref-local[all]

Install from Source
-------------------

.. code-block:: bash

    git clone https://github.com/ywatanabe1989/crossref-local.git
    cd crossref-local
    pip install -e ".[all]"

Database Setup
--------------

The database file is not included in the package. You need to obtain it separately:

1. Set the database path via environment variable:

.. code-block:: bash

    export CROSSREF_LOCAL_DB=/path/to/crossref.db

2. Or place the database at one of the default locations:

   - ``./data/crossref.db`` (project directory)
   - ``$SCITEX_DIR/crossref-local/runtime/crossref.db`` (runtime state dir)
   - ``~/.crossref_local/crossref.db`` (legacy, deprecated)

HTTP Mode (No Local Database)
-----------------------------

If you don't have the database locally, you can connect to a remote server:

.. code-block:: bash

    # Set API URL
    export CROSSREF_LOCAL_API_URL=http://your-server:31291

    # Or use --http flag
    crossref-local --http search "machine learning"

Verify Installation
-------------------

.. code-block:: bash

    # Check status
    crossref-local status

    # Test search
    crossref-local search "test query"
