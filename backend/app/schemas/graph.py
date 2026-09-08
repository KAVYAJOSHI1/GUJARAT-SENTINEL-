"""Schema for the Investigation Graph (Phase 14 §12)."""
from typing import Dict, List, Optional

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    type: str            # vehicle | detection | camera | location | alert |
                         # anomaly | incident | evidence | case | watchlist
    label: str
    href: Optional[str] = None
    meta: Dict[str, object] = {}


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str
    label: Optional[str] = None


class InvestigationGraph(BaseModel):
    root: str
    subject: str
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    node_count: int
    edge_count: int
    counts_by_type: Dict[str, int] = {}
    truncated: bool = False
    note: str
