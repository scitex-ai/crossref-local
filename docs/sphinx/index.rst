.. CrossRef Local documentation master file

CrossRef Local - Local CrossRef Database
========================================

**CrossRef Local** provides offline access to the CrossRef corpus — 167M+ scholarly works, DOI lookup, full-text search and citation networks — over the fleet's shared store.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   cli_reference
   http_api

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/crossref_local

Key Features
------------

- **167M+ Works**: The complete CrossRef corpus in this host's shared store
- **Full-Text Search**: Search across titles, abstracts, and authors (scans
  the works collection — see :doc:`http_api` for the cost)
- **Citation Networks**: Explore citation relationships and build networks
- **Impact Factors**: Pre-computed journal impact factors from OpenAlex
- **HTTP Relay**: Access a remote host's store via HTTP API
- **MCP Integration**: AI agents can search via MCP server
- **Python API**: Simple programmatic access

Quick Example
-------------

Python API:

.. code-block:: python

    from crossref_local import search, get

    # Full-text search
    results = search("machine learning", limit=10)
    for work in results:
        print(f"{work.title} ({work.year})")

    # Get by DOI
    work = get("10.1038/nature12373")
    print(work.citation())

CLI:

.. code-block:: bash

    # Search for papers
    crossref-local search "neural networks" -n 20

    # Search with impact factors
    crossref-local search "CRISPR" --impact-factor

    # Get by DOI
    crossref-local search-by-doi 10.1038/nature12373

    # Run HTTP relay server
    crossref-local relay

MCP Server:

.. code-block:: bash

    # Start MCP server for AI agent integration
    crossref-local mcp start

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
