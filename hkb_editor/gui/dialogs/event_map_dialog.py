from typing import Any
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord, HkbPointer, HkbArray
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, loading_indicator


_formats = [
    "Event -> Animations",
    "Animation -> Events",
    "Markdown",
],


class event_map_dialog(DpgItem):
    def __init__(
        self,
        behavior: HavokBehavior,
        *,
        title: str = "Event Map",
        tag: str = 0,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._graph = None
        self._user_data = user_data
        self._window: str = None

        self._build(title)

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            label=title,
            width=500,
            height=500,
            on_close=self._on_close,
            no_saved_settings=True,
            tag=self.tag,
        ) as self._window:
            dpg.add_input_text(
                multiline=True,
                width=-1,
                height=-1,
                tag=self._t("text"),
            )
            # dpg.add_combo(
            #     _formats,
            #     default_value=_formats[0],
            #     label="Format",
            #     callback=self._on_format_changed,
            #     tag=self._t("format"),
            # )

        center_window(self._window, split_frame=True)
        dpg.focus_item(self._tag)

        self._on_format_changed(self._t("format"), dpg.get_value(self._t("format")), None)

    # === DPG callbacks ================================================

    def _on_format_changed(self, sender: str, format: str, user_data: Any) -> None:
        dpg.set_value(self._t("text"), "")

        if not self._graph:
            self._graph = self._behavior.root_graph()
        
        # TODO format
        with loading_indicator("Collecting"):
            map = self._create_event_to_anims_map()
            text = "\n".join(f"{k}: {sorted(map[k])}" for k in sorted(map))
            dpg.set_value(self._t("text"), text)

    def _create_event_to_anims_map(self) -> None:
        sm_type_id = self._behavior.type_registry.find_first_type_by_name("hkbStateMachine")
        statemachines = self._behavior.find_objects_by_type(sm_type_id, True)
        events = self._behavior.get_events()
        
        map: dict[str, set[str]] = {}

        def collect_anim_ids(state_info: HkbRecord | str) -> set[str]:
            if isinstance(state_info, HkbRecord):
                state_info = state_info.object_id

            todo = [state_info]
            res = set()

            # Cheaper than rebuilding the graph everytime, we need to get the successors anyways
            while todo:
                object_id = todo.pop()
                obj: HkbRecord = self._behavior.objects[object_id]
                if obj.type_name == "CustomManualSelectorGenerator":
                    res.add(obj["animId"].get_value())
                else:
                    # Should be safe to skip all CMSG children
                    todo.extend(self._graph.successors(object_id))

            return res

        def delve_transitions(transition_info_array: HkbRecord) ->  None:
            transitions: HkbArray[HkbPointer] = transition_info_array["transitions"]
            for trans in transitions:
                evt_id = trans["eventId"].get_value()
                if not 0 <= evt_id < len(events):
                    continue

                state_id = trans["toStateId"].get_value()
                if state_id not in state_map:
                    continue

                state = state_map[state_id]
                evt = events[evt_id]
                map.setdefault(evt, set()).update(collect_anim_ids(state))

        for sm in statemachines:
            wildcard_trans: HkbRecord = sm["wildcardTransitions"].get_target()
            state_map = {}

            for state_ptr in sm["states"]:
                state: HkbRecord = state_ptr.get_target()
                if state:
                    state_map[state["stateId"].get_value()] = state

            if wildcard_trans:
                delve_transitions(wildcard_trans)

            for state in state_map.values():
                state_trans = state["transitions"].get_target()
                if state_trans:
                    delve_transitions(state_trans)

        return map

    def _on_close(self) -> None:
        self.destroy()
        dpg.delete_item(self._window)
