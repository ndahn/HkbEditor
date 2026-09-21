from __future__ import annotations
from typing import Any, Callable
from ast import literal_eval
from lxml import etree as ET
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb import HkbRecord
from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
)
from hkb_editor.gui import style
from hkb_editor.gui.widgets import (
    DpgItem,
    GraphWidget,
    add_paragraphs,
    loading_indicator,
)
from hkb_editor.workflows.clone_hierarchy import (
    MergeResult,
    MergeAction,
    Resolution,
    resolve_conflicts,
)


_instructions = """\
- NEW: add a copy with a new ID/index
- REUSE: use an already existing object
- IGNORE: don't add, but include children (this can create gaps)
- SKIP: don't add and ignore all children (unless reachable otherwise)
"""


class merge_hierarchy_dialog(DpgItem):
    """Review and resolve the conflicts of a pasted object hierarchy.

    Shows one table per conflict kind (events, variables, animations, types,
    objects), each row offering the :class:`MergeAction` choices that make
    sense for it. When a graph preview is available, selecting a node
    highlights every row that node references.

    Parameters
    ----------
    behavior : HavokBehavior
        Behavior the hierarchy is merged into.
    xml : lxml Element
        The pasted hierarchy; used for the graph preview.
    results : MergeResult
        Conflicts found by ``find_conflicts``; mutated as actions are picked.
    target_record : HkbRecord
        Record the hierarchy is attached to.
    callback : callable
        Called with no arguments once the merge has been applied.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    """

    # Conflict kind -> (label, MergeResult attribute)
    _SECTIONS = (
        ("event", "Events", "events"),
        ("variable", "Variables", "variables"),
        ("animation", "Animations", "animations"),
        ("type", "Types", "type_map"),
        ("object", "Objects", "objects"),
    )

    def __init__(
        self,
        behavior: HavokBehavior,
        xml: ET._Element,
        results: MergeResult,
        target_record: HkbRecord,
        callback: Callable[[], None],
        *,
        title: str = "Merge Hierarchy",
        tag: str = None,
    ) -> None:
        super().__init__(tag)

        self._behavior = behavior
        self._results = results
        self._target_record = target_record
        self._callback = callback

        self._window: str = None
        self._graph_preview: GraphWidget = None
        self._graph_data = xml.find("objects").get("graph")

        # Conflict kind -> {row tag: row index}, needed for highlighting
        self._rows: dict[str, dict[str, int]] = {
            kind: {} for kind, _, _ in self._SECTIONS
        }
        self._highlighted: dict[str, list[int]] = {}

        self._highlight_color = list(style.yellow)
        if len(self._highlight_color) < 4:
            self._highlight_color.append(100)
        else:
            self._highlight_color[3] = 100

        self._build(title)

    def destroy(self) -> None:
        # The graph widget owns a root level handler registry
        if self._graph_preview is not None:
            self._graph_preview.destroy()
            self._graph_preview = None

    # === Build ========================================================

    def _build(self, title: str) -> None:
        with dpg.window(
            width=1100 if self._graph_data else 600,
            height=690,
            label=title,
            modal=False,
            on_close=self.close,
            no_saved_settings=True,
            tag=self._tag,
        ) as self._window:
            with dpg.group(horizontal=True):
                if self._graph_data:
                    self._build_graph_preview()

                # List of conflicts and resolutions
                with dpg.child_window(border=False, height=520):
                    with dpg.group():
                        for i, (kind, label, attr) in enumerate(self._SECTIONS):
                            if i > 0:
                                dpg.add_spacer(height=10)

                            entries = getattr(self._results, attr)
                            with dpg.tree_node(
                                label=f"{label} ({len(entries)})",
                                # Objects is the interesting one
                                default_open=(kind == "object"),
                            ):
                                self._build_resolution_table(kind, entries)

            dpg.add_separator()
            add_paragraphs(_instructions, 150, color=style.light_blue)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Apply",
                    callback=self._on_apply,
                    tag=self._t("button_okay"),
                )
                dpg.add_button(
                    label="Cancel",
                    callback=self.close,
                    tag=self._t("button_close"),
                )
                dpg.add_checkbox(
                    label="Pin created objects",
                    default_value=True,
                    tag=self._t("pin_objects"),
                )

    def _build_graph_preview(self) -> None:
        graph = nx.from_edgelist(literal_eval(self._graph_data), nx.DiGraph)

        with dpg.child_window(
            width=500,
            height=500,
            resizable_x=True,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
            horizontal_scrollbar=False,
        ):
            self._graph_preview = GraphWidget(
                graph,
                on_node_selected=self._on_node_selected,
                get_node_frontpage=self._get_node_frontpage,
                hover_enabled=True,
                tag=self._t("graph_preview"),
            )

            # Reveal everything when first showing
            self._graph_preview.reveal_all_nodes(3)
            dpg.split_frame()  # wait for dimensions to be known
            self._graph_preview.show_all()

    def _build_resolution_table(
        self, kind: str, entries: dict[Any, Resolution]
    ) -> None:
        is_type = kind == "type"
        is_object = kind == "object"

        with dpg.table(
            header_row=False,
            policy=dpg.mvTable_SizingFixedFit,
            borders_innerH=True,
            tag=self._table_tag(kind),
        ):
            if is_object:
                dpg.add_table_column(label="oid", width_fixed=True)
                dpg.add_table_column(label="name", width_stretch=True)
            elif is_type:
                dpg.add_table_column(label="id0", width_fixed=True)
                dpg.add_table_column(label="to", width_fixed=True)
                dpg.add_table_column(label="id1", width_fixed=True)
                dpg.add_table_column(label="name", width_stretch=True)
            else:
                dpg.add_table_column(label="idx0", width_fixed=True)
                dpg.add_table_column(label="name0", width_stretch=True)
                dpg.add_table_column(label="to", width_fixed=True)
                dpg.add_table_column(label="idx1", width_fixed=True)
                dpg.add_table_column(label="name1", width_stretch=True)

            dpg.add_table_column(label="action", init_width_or_weight=100)

            for idx, (key, resolution) in enumerate(entries.items()):
                row_tag = self._row_tag(kind, key)

                with dpg.table_row(tag=row_tag):
                    if is_object:
                        dpg.add_text(key)
                        dpg.add_text(resolution.original.get_field("name", ""))
                        actions = [a.name for a in MergeAction]
                        if key not in self._behavior.objects:
                            # Can't reuse if there is no match
                            actions.remove(MergeAction.REUSE.name)
                    elif is_type:
                        dpg.add_text(str(resolution.original[0]))
                        dpg.add_text("->")
                        dpg.add_text(resolution.result[0])
                        dpg.add_text(f"({resolution.result[1]})")
                        actions = [MergeAction.REUSE.name]
                    else:
                        dpg.add_text(str(resolution.original[0]))
                        dpg.add_text(self._entry_name(resolution.original[1]))
                        dpg.add_text("->")
                        dpg.add_text(str(resolution.result[0]))
                        dpg.add_text(self._entry_name(resolution.result[1]))

                        actions = [a.name for a in MergeAction]
                        if resolution.result[0] < 0:
                            # Can't reuse if there's no match
                            actions.remove(MergeAction.REUSE.name)
                        else:
                            # Can't add if the constant already exists
                            actions.remove(MergeAction.NEW.name)

                    dpg.add_combo(
                        actions,
                        default_value=resolution.action.name,
                        callback=self._on_action_changed,
                        user_data=resolution,
                    )

                self._rows[kind][row_tag] = idx

    # === DPG callbacks ================================================

    def _on_action_changed(
        self, sender: str, action: str, resolution: Resolution
    ) -> None:
        resolution.action = MergeAction[action]

    def _get_node_frontpage(self, node) -> list[tuple[str, style.RGBA]]:
        obj: HkbRecord = self._results.objects[node.id].original

        try:
            return [
                (obj["name"].get_value(), style.yellow),
                (obj.type_name, style.white),
                (node.id, style.blue),
            ]
        except AttributeError:
            return [
                (obj.type_name, style.white),
                (node.id, style.blue),
            ]

    def _on_node_selected(self, node) -> None:
        self.clear_highlights()

        if not node:
            return

        obj: HkbRecord = self._results.objects[node.id].original

        # Highlight events, variables and animations this object references
        for kind, attributes in (
            ("event", event_attributes),
            ("variable", variable_attributes),
            ("animation", animation_attributes),
        ):
            if obj.type_name in attributes:
                for path in attributes[obj.type_name]:
                    for index in obj.get_fields(path, resolve=True).values():
                        if index >= 0:
                            self._highlight_row(kind, index)

        for resolution in self._results.type_map.values():
            if obj.type_id == resolution.result[0]:
                # Old type ID is unique, new one may not be
                self._highlight_row("type", resolution.original[0])
                break

        self._highlight_row("object", obj.object_id)

    def _on_apply(self) -> None:
        with loading_indicator("Merging Hierarchy"):
            with self._behavior.transaction():
                resolve_conflicts(
                    self._behavior, self._target_record, self._results
                )
                self._results.pin_objects = self.pin_objects
                self._callback()

        self.close()

    # === Helpers ======================================================

    @staticmethod
    def _entry_name(entry: Any) -> str:
        # Variables carry a record, events and animations are plain strings
        return getattr(entry, "name", entry)

    def _table_tag(self, kind: str) -> str:
        return self._t(f"{kind}_table")

    def _row_tag(self, kind: str, key: Any) -> str:
        return self._t(f"{kind}_row_{key}")

    def _highlight_row(self, kind: str, key: Any) -> None:
        table = self._table_tag(kind)
        row_idx = self._rows[kind].get(self._row_tag(kind, key))
        if row_idx is None:
            return

        dpg.highlight_table_row(table, row_idx, self._highlight_color)
        self._highlighted.setdefault(table, []).append(row_idx)

    # === Public =======================================================

    @property
    def pin_objects(self) -> bool:
        """Whether the caller should pin the merged objects."""
        return dpg.get_value(self._t("pin_objects"))

    def clear_highlights(self) -> None:
        for table, rows in self._highlighted.items():
            for row in rows:
                dpg.unhighlight_table_row(table, row)
            rows.clear()

    def close(self) -> None:
        self.destroy()
        dpg.delete_item(self._window)
