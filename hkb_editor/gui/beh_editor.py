from typing import Any
from dearpygui import dearpygui as dpg

from .graph_editor import GraphEditor, Node
from hkb.behavior import HavokBehavior
from hkb.hkb_types import HkbRecord


class BehaviorEditor(GraphEditor):
    def __init__(self, tag: str | int = 0):
        super().__init__(tag)

        self.beh: HavokBehavior = None
        self.roots: list[HkbRecord] = None

    def _do_load_from_file(self, file_path: str):
        self.beh = HavokBehavior(file_path)

    def _do_write_to_file(self, file_path):
        # TODO
        pass

    def get_supported_file_extensions(self):
        return [("Behavior XML", ".xml")]

    def get_roots(self) -> list[str]:
        sm_type = self.beh.type_registry.find_type_by_name("hkbStateMachine")
        self.roots = list(self.beh.find_objects_by_type(sm_type))
        return self.roots

    def _on_root_selected(self, sender: str, app_data: str, node_id: str) -> None:
        self.logger.info("Building graph for node %s", node_id)
        self.graph = self.beh.build_graph(node_id)
        super()._on_root_selected(sender, app_data, node_id)

    def get_node_attributes(self, node: Node) -> dict[str, Any]:
        obj: HkbRecord = self.beh.objects[node.id]
        return {k: v.get_value() for k,v in obj.get_value().items()}

    def set_node_attribute(self, node: Node, key: str, val: Any) -> None:
        obj: HkbRecord = self.beh.objects[node.id]
        # TODO implement setitem
        setattr(obj, key, val)

    def get_node_frontpage(self, node_id: str) -> list[str]:
        obj = self.beh.objects[node_id]
        try:
            return [
                obj.name.get_value(),
                node_id,
                self.beh.type_registry.get_name(obj.type_id),
            ]
        except AttributeError:
            return [
                node_id,
                self.beh.type_registry.get_name(obj.type_id),
            ]

    def get_node_frontpage_short(self, node_id: str) -> str:
        return self.beh.objects[node_id].name.get_value()

    def get_node_menu_items(self, node: Node) -> list[str]:
        return []

    def on_node_menu_item_selected(node: Node, selected_item: str) -> None:
        pass

    def on_node_selected(self, node: Node) -> None:
        pass

    # Fleshing out common use cases here

    def add_hks_variable(self, name: str):
        # TODO append to variableNames array
        pass

    def rename_hks_variable(self, name: str):
        # TODO variable order matters, so we can't just delete and add again
        pass

    def delete_hks_variable(self, name: str, update_nodes: bool = True):
        # TODO need to adjust indices of all nodes referencing this or a later one
        pass

    def wizard_create_generator(self, parent_id: str):
        # TODO a wizard that lets the user create a new generator and attach it to another node
        pass
