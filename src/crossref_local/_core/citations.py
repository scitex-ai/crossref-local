"""Citation network analysis and visualization.

Build citation graphs like Connected Papers from the local database.

Usage:
    from crossref_local.citations import get_citing, get_cited, CitationNetwork

    # Get papers citing a DOI
    citing_dois = get_citing("10.1038/nature12373")

    # Get papers a DOI cites
    cited_dois = get_cited("10.1038/nature12373")

    # Build and visualize network
    network = CitationNetwork("10.1038/nature12373", depth=2)
    network.save_html("citation_network.html")
"""

from dataclasses import dataclass as _dataclass
from dataclasses import field as _field
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from .models import Work
from .store import citations_store, works_store

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scitex_dev.store import Store

__all__ = [
    "get_citing",
    "get_cited",
    "get_citation_count",
    "CitationNode",
    "CitationEdge",
    "CitationNetwork",
]


def _edges(store: "Optional[Store]" = None):
    """Every citation edge, as ``(citing_doi, cited_doi)`` pairs.

    The store cannot filter, so both directions of the lookup below start
    from the whole collection. This is the single most costly consequence
    of the storage change for this module: what were two indexed lookups
    (``idx_citations_cited``, ``idx_citations_citing``) are now full reads,
    and the network builder issues one per node visited.
    """
    store = store if store is not None else citations_store()
    for row in store.rows():
        values = row.values
        yield str(values.get("citing_doi")), str(values.get("cited_doi"))


def get_citing(doi: str, limit: int = 100, store: "Optional[Store]" = None) -> List[str]:
    """
    Get DOIs of papers that cite the given DOI.

    Args:
        doi: The DOI to find citations for
        limit: Maximum number of citing papers to return
        store: Citations store (opens this host's if not provided)

    Returns:
        List of DOIs that cite this paper
    """
    found = [citing for citing, cited in _edges(store) if cited == doi]
    found.sort()
    return found[:limit]


def get_cited(doi: str, limit: int = 100, store: "Optional[Store]" = None) -> List[str]:
    """
    Get DOIs of papers that the given DOI cites (references).

    Args:
        doi: The DOI to find references for
        limit: Maximum number of referenced papers to return
        store: Citations store (opens this host's if not provided)

    Returns:
        List of DOIs that this paper cites
    """
    found = [cited for citing, cited in _edges(store) if citing == doi]
    found.sort()
    return found[:limit]


def get_citation_count(doi: str, store: "Optional[Store]" = None) -> int:
    """
    Get the number of citations for a DOI.

    Args:
        doi: The DOI to count citations for
        store: Citations store

    Returns:
        Number of papers citing this DOI
    """
    return sum(1 for _citing, cited in _edges(store) if cited == doi)


@_dataclass
class CitationNode:
    """A node in the citation network."""

    doi: str
    title: str = ""
    authors: List[str] = _field(default_factory=list)
    year: Optional[int] = None
    journal: str = ""
    citation_count: int = 0
    depth: int = 0  # Distance from center node

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "citation_count": self.citation_count,
            "depth": self.depth,
        }


@_dataclass
class CitationEdge:
    """An edge in the citation network (citing -> cited)."""

    citing_doi: str
    cited_doi: str
    year: Optional[int] = None


class CitationNetwork:
    """
    Citation network builder and visualizer.

    Builds a graph of papers connected by citations, similar to Connected Papers.

    Example:
        >>> network = CitationNetwork("10.1038/nature12373", depth=2)
        >>> print(f"Nodes: {len(network.nodes)}, Edges: {len(network.edges)}")
        >>> network.save_html("network.html")
    """

    def __init__(
        self,
        center_doi: str,
        depth: int = 1,
        max_citing: int = 50,
        max_cited: int = 50,
        store: "Optional[Store]" = None,
    ):
        """
        Build a citation network around a central paper.

        Args:
            center_doi: The DOI to build the network around
            depth: How many levels of citations to include (1 = direct only)
            max_citing: Max papers citing each node to include
            max_cited: Max papers each node cites to include
            store: Citations store (opens this host's if not provided)
        """
        self.center_doi = center_doi
        self.depth = depth
        self.max_citing = max_citing
        self.max_cited = max_cited
        self.store = store if store is not None else citations_store()
        self.works = works_store()

        self.nodes: Dict[str, CitationNode] = {}
        self.edges: List[CitationEdge] = []

        self._build_network()

    def _build_network(self):
        """Build the citation network by traversing citations.

        The edge list is read ONCE and indexed in memory, rather than asked
        for per node. The store cannot filter, so a per-node lookup would
        re-read the whole collection for every node visited — quadratic in
        the traversal, on the largest collection this package has.
        """
        by_cited: Dict[str, List[str]] = {}
        by_citing: Dict[str, List[str]] = {}
        for citing, cited in _edges(self.store):
            by_cited.setdefault(cited, []).append(citing)
            by_citing.setdefault(citing, []).append(cited)
        for bucket in (by_cited, by_citing):
            for dois in bucket.values():
                dois.sort()
        self._by_cited = by_cited
        self._by_citing = by_citing

        # Start with center node
        to_process: List[Tuple[str, int]] = [(self.center_doi, 0)]
        processed: Set[str] = set()

        while to_process:
            doi, current_depth = to_process.pop(0)

            if doi in processed:
                continue
            processed.add(doi)

            # Add node
            self._add_node(doi, current_depth)

            # Stop expanding at max depth
            if current_depth >= self.depth:
                continue

            # Get citing papers (papers that cite this one)
            citing = by_cited.get(doi, [])[: self.max_citing]
            for citing_doi in citing:
                self.edges.append(CitationEdge(citing_doi=citing_doi, cited_doi=doi))
                if citing_doi not in processed:
                    to_process.append((citing_doi, current_depth + 1))

            # Get cited papers (papers this one cites)
            cited = by_citing.get(doi, [])[: self.max_cited]
            for cited_doi in cited:
                self.edges.append(CitationEdge(citing_doi=doi, cited_doi=cited_doi))
                if cited_doi not in processed:
                    to_process.append((cited_doi, current_depth + 1))

    def _add_node(self, doi: str, depth: int):
        """Add a node with metadata from the store."""
        if doi in self.nodes:
            return

        row = self.works.get({"doi": doi})
        metadata = row.values.get("metadata") if row is not None else None
        citation_count = len(self._by_cited.get(doi, ()))

        if metadata:
            work = Work.from_metadata(doi, metadata)
            self.nodes[doi] = CitationNode(
                doi=doi,
                title=work.title or "",
                authors=work.authors,
                year=work.year,
                journal=work.journal or "",
                citation_count=citation_count,
                depth=depth,
            )
        else:
            # DOI not in our database, create minimal node
            self.nodes[doi] = CitationNode(
                doi=doi,
                citation_count=citation_count,
                depth=depth,
            )

    def to_networkx(self):
        """
        Convert to a NetworkX DiGraph.

        Returns:
            networkx.DiGraph with nodes and edges

        Raises:
            ImportError: If networkx is not installed
        """
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("networkx required: pip install networkx")

        G = nx.DiGraph()

        # Add nodes with attributes
        for doi, node in self.nodes.items():
            G.add_node(doi, **node.to_dict())

        # Add edges
        for edge in self.edges:
            if edge.citing_doi in self.nodes and edge.cited_doi in self.nodes:
                G.add_edge(edge.citing_doi, edge.cited_doi)

        return G

    def save_html(self, path: str = "citation_network.html", **kwargs):
        """
        Save interactive HTML visualization using pyvis.

        Args:
            path: Output file path
            **kwargs: Additional options for pyvis Network

        Raises:
            ImportError: If pyvis is not installed
        """
        import math as _math

        try:
            from pyvis.network import Network
        except ImportError:
            raise ImportError("pyvis required: pip install pyvis")

        # Create pyvis network
        net = Network(
            height="800px",
            width="100%",
            directed=True,
            bgcolor="#ffffff",
            font_color="#333333",
            **kwargs,
        )

        # Configure physics
        net.barnes_hut(
            gravity=-3000,
            central_gravity=0.3,
            spring_length=200,
            spring_strength=0.05,
        )

        # Add nodes with styling based on depth and citation count
        for doi, node in self.nodes.items():
            # Size based on citation count (log scale)
            size = 10 + min(30, _math.log1p(node.citation_count) * 5)

            # Color based on depth
            colors = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12"]
            color = colors[min(node.depth, len(colors) - 1)]

            # Label
            title_short = (
                (node.title[:50] + "...") if len(node.title) > 50 else node.title
            )
            label = f"{title_short}\n({node.year or 'N/A'})"

            # Tooltip
            authors_str = ", ".join(node.authors[:3])
            if len(node.authors) > 3:
                authors_str += " et al."
            tooltip = f"""
            <b>{node.title}</b><br>
            {authors_str}<br>
            {node.journal} ({node.year or "N/A"})<br>
            Citations: {node.citation_count}<br>
            DOI: {doi}
            """

            net.add_node(
                doi,
                label=label,
                title=tooltip,
                size=size,
                color=color,
                borderWidth=2 if doi == self.center_doi else 1,
                borderWidthSelected=4,
            )

        # Add edges
        for edge in self.edges:
            if edge.citing_doi in self.nodes and edge.cited_doi in self.nodes:
                net.add_edge(edge.citing_doi, edge.cited_doi, arrows="to")

        # Save
        net.save_graph(path)
        return path

    def save_png(
        self, path: str = "citation_network.png", figsize: Tuple[int, int] = (12, 10)
    ):
        """
        Save static PNG visualization using matplotlib.

        Args:
            path: Output file path
            figsize: Figure size (width, height)

        Raises:
            ImportError: If matplotlib is not installed
        """
        import math as _math

        try:
            import matplotlib.pyplot as plt
            import networkx as nx
        except ImportError:
            raise ImportError("matplotlib and networkx required")

        G = self.to_networkx()

        fig, ax = plt.subplots(figsize=figsize)

        # Layout
        pos = nx.spring_layout(G, k=2, iterations=50)

        # Node sizes based on citation count
        sizes = [
            100 + min(500, _math.log1p(self.nodes[n].citation_count) * 50)
            for n in G.nodes()
        ]

        # Node colors based on depth
        colors = [self.nodes[n].depth for n in G.nodes()]

        # Draw
        nx.draw_networkx_nodes(
            G,
            pos,
            node_size=sizes,
            node_color=colors,
            cmap=plt.cm.RdYlBu_r,
            alpha=0.8,
            ax=ax,
        )
        nx.draw_networkx_edges(G, pos, alpha=0.3, arrows=True, arrowsize=10, ax=ax)

        # Labels for important nodes (high citation count)
        labels = {}
        for doi in G.nodes():
            node = self.nodes[doi]
            if node.citation_count > 10 or doi == self.center_doi:
                short_title = (
                    (node.title[:30] + "...") if len(node.title) > 30 else node.title
                )
                labels[doi] = f"{short_title}\n({node.year or 'N/A'})"

        nx.draw_networkx_labels(G, pos, labels, font_size=8, ax=ax)

        ax.set_title(f"Citation Network: {self.center_doi}")
        ax.axis("off")

        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()

        return path

    def to_dict(self) -> dict:
        """Export network as dictionary."""
        return {
            "center_doi": self.center_doi,
            "depth": self.depth,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [
                {"citing": e.citing_doi, "cited": e.cited_doi} for e in self.edges
            ],
            "stats": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
            },
        }

    def __repr__(self):
        return f"CitationNetwork(center={self.center_doi}, nodes={len(self.nodes)}, edges={len(self.edges)})"
