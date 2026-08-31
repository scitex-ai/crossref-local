Installation
============

Requirements
------------

- Python 3.10+
- ``scitex-dev>=0.57.0``
- Access to this host's shared store (the corpus lives there)

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

Store Setup
-----------

The corpus is not a file and is not shipped in the package. It lives in this
host's shared store — one PostgreSQL-backed store per host, resolved by
:func:`scitex_dev.store.host_store`. There is no path to configure and no
dump to download.

1. Optionally point at a store other than this host's own:

.. code-block:: bash

    export SCITEX_STORE_DSN=...

``crossref-local`` never builds or reads a DSN itself; ``scitex-dev`` owns
that resolution. Leave the variable unset to use this host's store.

2. Populate and refresh the corpus incrementally from the CrossRef REST API:

.. code-block:: bash

    crossref-local update-db --yes

    # Refresh the exact-count cache that status and info() read
    crossref-local sync-stats

HTTP Mode (No Local Store)
--------------------------

If this machine has no store of its own, you can connect to a remote server:

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
