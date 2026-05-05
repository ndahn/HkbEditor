from typing import Any
from dataclasses import dataclass
import networkx as nx


@dataclass
class Node:
    id: str
    level: int = 0
    pos: tuple[float, float] = None
    size: tuple[float, float] = None
    visible: bool = False
    unfolded: bool = False
    user_data: Any = None

    @property
    def x(self) -> float:
        return self.pos[0]

    @property
    def y(self) -> float:
        return self.pos[1]

    @property
    def width(self) -> float:
        return self.size[0]

    @property
    def height(self) -> float:
        return self.size[1]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (
            self.pos[0],
            self.pos[1],
            self.pos[0] + self.size[0],
            self.pos[1] + self.size[1],
        )

    def contains(self, px: float, py: float) -> bool:
        bbox = self.bbox
        return bbox[0] <= px < bbox[2] and bbox[1] <= py < bbox[3]

    def __str__(self):
        return self.id

    def __hash__(self):
        return hash(self.id)


@dataclass
class GraphLayout:
    gap_x: int = 30
    step_y: int = 20
    node0_margin: tuple[int, int] = (0, 0)
    text_margin: int = 5
    zoom_factor: float = 1.3

    def compute_layout(
        self, graph: nx.DiGraph, nodemap: dict[str, Node]
    ) -> dict[str, tuple[float, float]]:
        """Return {node_id: (x, y)} for all visible nodes."""
        return {}


@dataclass
class HorizontalGraphLayout(GraphLayout):
    def compute_layout(
        self, graph: nx.DiGraph, nodemap: dict[str, Node]
    ) -> dict[str, tuple[float, float]]:
        """
        Place nodes left-to-right by column, top-to-bottom within each column.

        Column is derived from the deepest visible parent's column + 1, so
        multi-parent nodes land in the correct column for the branch that
        revealed them rather than using a pre-assigned shortest-path depth.

        next_y[col] tracks the next free y-coordinate per column so siblings
        from different parents never overlap.
        """
        scale = self.zoom_factor
        gap_x = self.gap_x * scale
        step_y = self.step_y * scale

        positions: dict[str, tuple[float, float]] = {}
        col_map: dict[str, int] = {}  # node_id -> column index
        col_max_x: dict[int, float] = {}  # col index -> max right edge in that col
        next_y: dict[int, float] = {}  # col index -> next free y

        for node_id in nx.topological_sort(graph):
            node = nodemap[node_id]
            if not node.visible:
                continue

            # Pick the visible parent with the greatest column (deepest in the
            # current view). This handles multi-parent nodes correctly: the node
            # lands one step to the right of whichever parent is furthest right.
            visible_parents = [
                p for p in graph.predecessors(node_id) if nodemap[p].visible
            ]

            if not visible_parents:
                col = 0
                x = float(self.node0_margin[0])
                ymin = float(self.node0_margin[1])
            else:
                parent_id = max(visible_parents, key=lambda p: col_map.get(p, 0))
                col = col_map[parent_id] + 1
                x = col_max_x.get(col - 1, float(self.node0_margin[0])) + gap_x
                ymin = nodemap[parent_id].y

            col_map[node_id] = col

            # y: below the last sibling in this column, but never above ymin
            y = max(next_y.get(col, float(self.node0_margin[1])), ymin)

            positions[node_id] = (x, y)
            node.pos = (x, y)  # keep node in sync so size-based x updates work

            # Advance the cursor once we know the node's height (may be None on
            # first pass before the node has been drawn; fall back to step_y).
            h = node.height if node.size else step_y
            next_y[col] = y + h + step_y

            w = node.width if node.size else 0.0
            col_max_x[col] = max(col_max_x.get(col, 0.0), x + w)

        return positions
