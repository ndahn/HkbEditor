from dearpygui import dearpygui as dpg

from .graph_editor import GraphEditor
from hkb_editor.behavior import Behavior


class BehaviorEditor(GraphEditor):
    def __init__(self, tag: str | int = 0):
        super().__init__(tag)

        self.beh: Behavior = None
        self._node_menus = {}

    def load_behavior(self, path: str):
        # TODO verify it's the expected xml file
        from ..parser import parse_behavior

        beh = parse_behavior(path)

        sm_type = beh.types.by_name["hkbStateMachine"]
        items = []

        for sm in beh.objects.by_type[sm_type]:
            key = f"{sm.name ({sm.id})}"
            items.append(key)

        dpg.configure_item(f"{self.tag}_roots_list", items=items)

    def get_node_attributes(self, node: str | int):
        return self.beh.objects[node].fields()

    def get_node_frontpage(self, node_id: str | int):
        node = self.beh.objects.by_id[node_id]
        node_name = node.get_name()
        node_type = node.typeid
        node_type_name = self.beh.types.by_id[node_type].name

        lines = [
            f"{node_id}",
            f"<{node_type_name}>",
        ]

        if node_name:
            lines.append(f"{node_name}")

        return lines

    def get_node_children(self, node_id: str):
        # TODO
        node = self.beh.objects[node_id]

    def on_node_created(self, node_id: str | int):
        node = self.beh.objects[node_id]

        # Add a right click menu
        with dpg.popup(
            parent=node_id, 
            mousebutton=dpg.mvMouseButton_Right, 
        ) as node_menu:
            dpg.add_text(node_id)
            dpg.add_separator()

            if isinstance(node, HkbStateMachine):
                # TODO add stateinfo
                pass
            elif isinstance(node, HkbStateInfo):
                pass
            elif isinstance(node, HkbVariableBindingSet):
                pass
            elif isinstance(node, HkbLayerGenerator):
                pass
            elif isinstance(node, HkbLayer):
                pass
            elif isinstance(node, HkbManualSelectorGenerator):
                pass
            elif isinstance(node, CustomManualSelectorGenerator):
                pass
            elif isinstance(node, HkbScriptGenerator):
                pass

            dpg.add_separator()
            dpg.add_button(label="Delete", callback=delete_node)

        self._node_menus[node] = node_menu

    def _clear_canvas(self):
        for item in self._node_menus.values():
            dpg.delete_item(item)
        self._node_menus.clear()
        
        super()._clear_canvas()

    def _delete_node(self, node_id: str | int):
        menu = self._node_menus.pop(node_id, None)
        if menu is not None:
            dpg.delete_item(menu)
        super()._delete_node(node_id)

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
