from typing import Any, Callable
import re
import networkx as nx
from dearpygui import dearpygui as dpg

from hkb_editor.hkb.hkb_types import HkbRecord
from hkb_editor.gui import style
from hkb_editor.gui.helpers import center_window
from hkb_editor.gui.widgets import DpgItem, add_paragraphs


_instructions = """\
Use regular expressions to replace parts of record names. Supports capture groups to keep parts of the matched string. Be aware that the names of StateInfos are relevant for HKS!
"""

_search_syntax = [
    ("(abc)", "capture group"),
    ("(?:abc)", "non-capturing group"),
    (".", "any character"),
    ("[abc]", "any of abc"),
    ("\\d  \\w  \\s", "digit, word, space"),
    ("*  +  ?", "0+, 1+, optional"),
]

_replace_syntax = [
    ("\\1 \\2", "insert capture group"),
    ("\\g<0>", "entire match"),
]


def _add_tooltip_table(items: list[tuple[str, str]]) -> None:
    with dpg.table(header_row=False):
        dpg.add_table_column()
        dpg.add_table_column()

        for row in items:
            with dpg.table_row():
                dpg.add_text(row[0])
                dpg.add_text(row[1])


class mass_rename_dialog(DpgItem):
    """A dialog for renaming a record hierarchy via regular expressions.

    Offers a search/replace pattern pair with a live preview and applies the
    substitution to the ``name`` field of every record reachable from ``root``,
    in topological order and inside a single transaction. On confirm,
    ``callback`` receives the list of records that were actually altered.

    Parameters
    ----------
    root : HkbRecord
        Record whose subgraph will be renamed.
    callback : callable, optional
        Called as ``callback(tag, altered, user_data)`` on confirm.
    initial_search : str, optional
        Pre-filled search pattern.
    initial_replace : str, optional
        Pre-filled replacement pattern.
    title : str
        Window title bar label.
    tag : int or str, optional
        Explicit tag; auto-generated if None.
    user_data : any, optional
        Passed through to ``callback``.
    """

    def __init__(
        self,
        root: HkbRecord,
        callback: Callable[[str, list[HkbRecord], Any], None] = None,
        *,
        initial_search: str = None,
        initial_replace: str = None,
        title: str = "Mass Rename",
        tag: str = None,
        user_data: Any = None,
    ) -> None:
        super().__init__(tag)

        self._root = root
        self._callback = callback
        self._user_data = user_data
        self._window: str = None

        self._build(title, initial_search, initial_replace)

    # === Build ========================================================

    def _build(self, title: str, initial_search: str, initial_replace: str) -> None:
        with dpg.window(
            label=title,
            width=400,
            height=600,
            autosize=True,
            no_saved_settings=True,
            tag=self._tag,
            on_close=lambda: dpg.delete_item(self._window),
        ) as self._window:
            dpg.add_input_text(
                label="Search",
                default_value=initial_search or "",
                callback=self._on_pattern_changed,
                tag=self._t("search"),
            )
            with dpg.tooltip(dpg.last_item()):
                _add_tooltip_table(_search_syntax)

            dpg.add_input_text(
                label="Replace",
                default_value=initial_replace or "",
                callback=self._on_pattern_changed,
                tag=self._t("replace"),
            )
            with dpg.tooltip(dpg.last_item()):
                _add_tooltip_table(_replace_syntax)

            dpg.add_text("Try it out!")
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    hint="Test",
                    default_value=self._root["name"].get_value(),
                    callback=self._on_pattern_changed,
                    tag=self._t("preview_input"),
                )
                dpg.add_text("->")
                dpg.add_input_text(
                    hint="Preview",
                    default_value="",
                    enabled=False,
                    readonly=True,
                    tag=self._t("preview_output"),
                )

            dpg.add_spacer(height=3)
            add_paragraphs(_instructions, 50, color=style.light_blue)

            dpg.add_separator()
            dpg.add_spacer(height=2)
            dpg.add_text(show=False, tag=self._t("notification"), color=style.red)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Okay",
                    callback=self._on_okay,
                    tag=self._t("button_okay"),
                )
                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.delete_item(self._window),
                )
                dpg.add_checkbox(
                    label="Pin created objects",
                    default_value=True,
                    tag=self._t("pin_objects"),
                )

        center_window(self._window)
        dpg.focus_item(self._t("search"))

    # === DPG callbacks ================================================

    def _on_pattern_changed(self) -> None:
        try:
            search_pat = re.compile(self.search_pattern)
        except re.PatternError:
            dpg.set_value(self._t("preview_output"), "<error>")
            return

        txt_in = dpg.get_value(self._t("preview_input"))
        preview = re.sub(search_pat, self.replace_pattern, txt_in)
        dpg.set_value(self._t("preview_output"), preview)

    def _on_okay(self) -> None:
        try:
            altered = self.apply()
        except re.PatternError as e:
            self.show_message(e.msg)
            return

        self.show_message()

        if self._callback:
            self._callback(self._tag, altered, self._user_data)

    # === Public =======================================================

    @property
    def search_pattern(self) -> str:
        return dpg.get_value(self._t("search"))

    @property
    def replace_pattern(self) -> str:
        return dpg.get_value(self._t("replace"))

    @property
    def pin_objects(self) -> bool:
        """Whether the caller should pin the renamed records."""
        return dpg.get_value(self._t("pin_objects"))

    def apply(self) -> list[HkbRecord]:
        """Rename every named record below the root. Returns the altered ones."""
        search_pat = re.compile(self.search_pattern)
        replace_str = self.replace_pattern

        tagfile = self._root.tagfile
        altered: list[HkbRecord] = []

        with tagfile.transaction():
            g = tagfile.build_graph(self._root.object_id)
            for layer in nx.topological_generations(g):
                for nid in layer:
                    node = tagfile.objects[nid]
                    name_field = node.get_field("name", None)
                    if name_field:
                        new_name = re.sub(
                            search_pat, replace_str, name_field.get_value()
                        )
                        name_field.set_value(new_name)
                        altered.append(node)

        return altered

    def show_message(self, msg: str = None, color: style.RGBA = style.red) -> None:
        """Show or hide the notification label. Pass ``msg=None`` to hide."""
        if not msg:
            dpg.hide_item(self._t("notification"))
            return

        dpg.configure_item(
            self._t("notification"),
            default_value=msg,
            color=color,
            show=True,
        )
