HTTP API Reference
==================

CrossRef Local provides a RESTful HTTP API via the relay server.

Starting the Server
-------------------

.. code-block:: bash

    crossref-local relay --port 31291

The API documentation is available at ``http://localhost:31291/docs``.

Endpoints
---------

Root
~~~~

.. code-block:: text

    GET /

Returns API information and available endpoints.

Health Check
~~~~~~~~~~~~

.. code-block:: text

    GET /health

Returns server health status.

Store Info
~~~~~~~~~~

.. code-block:: text

    GET /info

Returns corpus statistics — works, searchable works, citation edges — read
from the exact-count cache, plus a ``counts_source`` of ``"exact"`` or
``"unavailable"``. The counts are never measured on this path; refresh the
cache with ``crossref-local sync-stats``.

Search Works
~~~~~~~~~~~~

.. code-block:: text

    GET /works?q=<query>&limit=<n>&offset=<n>

Parameters:

- ``q`` (required): Search query (see `Query Syntax`_ below)
- ``limit`` (optional): Max results (default: 10, max: 100)
- ``offset`` (optional): Skip first N results

Example:

.. code-block:: bash

    curl "http://localhost:31291/works?q=machine%20learning&limit=10"

Response:

.. code-block:: json

    {
      "query": "machine learning",
      "total": 1234567,
      "returned": 10,
      "elapsed_ms": 45.2,
      "results": [
        {
          "doi": "10.1234/example",
          "title": "Machine Learning Methods",
          "authors": ["Author One", "Author Two"],
          "year": 2023,
          "journal": "Nature",
          "abstract": "..."
        }
      ]
    }

Get Work by DOI
~~~~~~~~~~~~~~~

.. code-block:: text

    GET /works/{doi}

Example:

.. code-block:: bash

    curl "http://localhost:31291/works/10.1038/nature12373"

Batch Lookup
~~~~~~~~~~~~

.. code-block:: text

    POST /works/batch

Request body:

.. code-block:: json

    {
      "dois": ["10.1038/nature12373", "10.1126/science.aax0758"]
    }

Citations
---------

Get Citing Papers
~~~~~~~~~~~~~~~~~

.. code-block:: text

    GET /citations/{doi}/citing?limit=<n>

Returns DOIs of papers that cite the given work.

Get Cited Papers
~~~~~~~~~~~~~~~~

.. code-block:: text

    GET /citations/{doi}/cited?limit=<n>

Returns DOIs of papers that the given work cites (references).

Citation Count
~~~~~~~~~~~~~~

.. code-block:: text

    GET /citations/{doi}/count

Returns the number of citations for a work.

Citation Network
~~~~~~~~~~~~~~~~

.. code-block:: text

    GET /citations/{doi}/network?depth=<n>&max_citing=<n>&max_cited=<n>

Returns a citation network graph.

Query Syntax
------------

The search supports:

- Simple terms: ``machine learning`` (adjacent terms are joined by ``AND``)
- Exact phrases: ``"neural network"``
- Boolean operators: ``CRISPR AND gene editing``, ``hippocampus OR cortex``
- Exclusion: ``machine learning NOT deep``

Terms match as case-insensitive substrings of a work's title, abstract,
authors and container title. There is no prefix operator: ``neuro*`` is
matched literally, and a bare ``neuro`` already matches ``neuroscience``.
``NEAR`` is accepted but treated as ``AND`` — proximity needs positional
information the store does not keep, so the match is widened rather than
silently returning proximity-ordered nonsense.

.. warning::

   Search is **not indexed**. The store primitive has no text-search
   surface, no filtered read and no aggregate, so matching happens in Python
   over every record in the works collection: one full scan per query. This
   is correct at any size and acceptable only at small ones — against the
   full ~167M-work corpus it is not viable. A query surface on the store
   primitive is the outstanding work.

Examples:

.. code-block:: bash

    # Simple search
    curl "http://localhost:31291/works?q=CRISPR"

    # Phrase search
    curl "http://localhost:31291/works?q=\"deep%20learning\""

    # Boolean
    curl "http://localhost:31291/works?q=machine%20AND%20learning%20NOT%20deep"
