Quickstart
==========

This guide covers the basic usage of CrossRef Local.

Python API
----------

Basic Search
~~~~~~~~~~~~

.. code-block:: python

    from crossref_local import search

    # Full-text search
    results = search("machine learning", limit=10)

    print(f"Found {results.total} matches")

    for work in results:
        print(f"- {work.title} ({work.year})")
        print(f"  DOI: {work.doi}")
        print(f"  Journal: {work.journal}")

Get by DOI
~~~~~~~~~~

.. code-block:: python

    from crossref_local import get

    work = get("10.1038/nature12373")

    if work:
        print(f"Title: {work.title}")
        print(f"Authors: {', '.join(work.authors)}")
        print(f"Year: {work.year}")
        print(f"Citations: {work.citation_count}")

HTTP Mode
~~~~~~~~~

.. code-block:: python

    from crossref_local import configure_http, search

    # Configure to use HTTP API
    configure_http("http://localhost:31291")

    # Same API works transparently
    results = search("CRISPR")

Command Line Interface
----------------------

Search
~~~~~~

.. code-block:: bash

    # Basic search
    crossref-local search "neural networks"

    # With options
    crossref-local search "machine learning" -n 20 -a --impact-factor

    # Output as JSON
    crossref-local search "deep learning" --json

Get by DOI
~~~~~~~~~~

.. code-block:: bash

    crossref-local search-by-doi 10.1038/nature12373

    # As citation format
    crossref-local search-by-doi 10.1038/nature12373 --citation

HTTP Relay Server
~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Start relay server
    crossref-local relay

    # Custom port
    crossref-local relay --port 8080

    # Then connect from another machine
    crossref-local --http search "query"

MCP Server
~~~~~~~~~~

.. code-block:: bash

    # Start MCP server
    crossref-local mcp start

    # With specific transport
    crossref-local mcp start -t sse --port 8082

Environment Variables
---------------------

- ``SCITEX_STORE_DSN``: Connection string for the shared store, resolved by
  :func:`scitex_dev.store.host_store` (default: this host's own store)
- ``CROSSREF_LOCAL_API_URL``: HTTP API URL for remote access
- ``CROSSREF_LOCAL_MODE``: Force mode (``db`` or ``http``)
- ``CROSSREF_LOCAL_HOST``: Host for relay server (default: 0.0.0.0)
- ``CROSSREF_LOCAL_PORT``: Port for relay server (default: 31291)
