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
    node0_margin: tuple[int, int] = (50, 50)
    text_margin: int = 5
    zoom_factor: float = 1.3
    
    def get_pos_for_node(
        self, graph: nx.DiGraph, node: Node, nodemap: dict[str, Node]
    ) -> tuple[float, float]:
        return None


@dataclass
class HorizontalGraphLayout:
    def get_pos_for_node(
        self, graph: nx.DiGraph, node: Node, nodemap: dict[str, Node]
    ) -> tuple[float, float]:
        parent_id = next(
            (n for n in graph.predecessors(node.id) if nodemap[n].visible), None
        )
        
        if parent_id and parent_id in nodemap:
            parent = nodemap[parent_id]
            level = parent.level + 1
            ymin = parent.y
        else:
            level = node.level
            ymin = 0

        if level == 0:
            px, py = self.node0_margin
        else:
            px = py = 0.0

            for n in nodemap.values():
                if n.visible:
                    nl = n.level

                    if nl == level:
                        # Move down
                        py = max(py, n.y + n.height)

                    elif nl == (level - 1):
                        # Move to the right
                        px = max(px, n.x + n.width)

            px += self.gap_x * self.zoom_factor

            if py > 0.0:
                py += self.step_y * self.zoom_factor

            py = max(ymin, py)

        return px, py
