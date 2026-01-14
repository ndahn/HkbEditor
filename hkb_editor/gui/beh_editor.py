from typing import Any
import sys
import os
from ast import literal_eval
import logging
import shutil
import traceback
from threading import Thread
import textwrap
import time
import re
import pyperclip
from dearpygui import dearpygui as dpg
import networkx as nx

from hkb_editor.hkb.behavior import HavokBehavior
from hkb_editor.hkb.hkb_types import (
    XmlValueHandler,
    HkbRecord,
    HkbArray,
    HkbPointer,
)
from hkb_editor.hkb.skeleton import load_skeleton_bones
from hkb_editor.hkb.hkb_enums import hkbVariableInfo_VariableType as VariableType
from hkb_editor.hkb.xml import xml_from_str
from hkb_editor.hkb.index_attributes import (
    event_attributes,
    variable_attributes,
    animation_attributes,
    fix_index_references,
)
from hkb_editor.templates.glue import get_templates

from hkb_editor.external import (
    Config,
    load_config,
    xml_to_hkx,
    hkx_to_xml,
    unpack_binder,
    pack_binder,
)

try:
    from hkb_editor.external.reload import ChrReloader, detect_game_config
except (ImportError, AttributeError) as e:
    # Not available on non-Windows systems
    ChrReloader = None
    logging.getLogger().error(
        f"Failed to load character reloader: {e}",
    )

from hkb_editor.hkb.version_updates import fix_variable_defaults

from .widgets.graph_widget import GraphWidget, GraphLayout, Node
from .widgets.attributes_widget import AttributesWidget
from .widgets.graphmap import GraphMap  # TODO
from .dialogs import (
    about_dialog,
    open_file_dialog,
    save_file_dialog, 
    edit_simple_array_dialog,
    search_objects_dialog, 
)
from .tools import (
    skeleton_mirror_dialog,
    eventlistener_dialog,
    open_state_graph_viewer,
)
from .workflows.aliases import AliasManager, AliasMap
from .workflows.create_cmsg import create_cmsg_dialog
from .workflows.register_clip import register_clip_dialog
from .workflows.create_object import create_object_dialog
from .workflows.apply_template import apply_template_dialog
from .workflows.update_name_ids import update_name_ids_dialog
from .workflows.clone_hierarchy import (
    import_hierarchy,
    paste_hierarchy,
    paste_children,
    MergeAction,
)
from .workflows.verify_behavior import verify_behavior
from .helpers import make_copy_menu, center_window, common_loading_indicator
from . import style



def get_default_layout_path():
    return os.path.join(os.path.dirname(sys.argv[0]), "default_layout.ini")


def get_custom_layout_path():
    return os.path.join(os.path.dirname(sys.argv[0]), "user_layout.ini")


class BehaviorEditor:
    def __init__(self, tag: str | int = 0):
        # Setup the root logger first before calling super, which will instantiate
        # a new logger
        class LogHandler(logging.Handler):
            def emit(this, record):
                self.notification(record.getMessage(), record.levelno)

        logging.root.addHandler(LogHandler())

        self.beh: HavokBehavior = None
        self._busy = False
        self.alias_manager = AliasManager()
        self.attributes_widget: AttributesWidget = None
        self.pinned_objects_table: str = None
        self.min_notification_severity = logging.INFO
        self.loaded_skeleton_path: str = None

        self.chr_reloader = None
        self.config: Config = load_config()

        if tag in (0, None, ""):
            tag = dpg.generate_uuid()

        self.logger = logging.getLogger(self.__class__.__name__)
        self.tag: str = tag
        self.roots_table: str = None
        self.canvas: GraphWidget = None
        self.attributes_table: str = None
        self.loaded_file: str = None
        self.last_save: float = 0.0
        self.selected_roots: set[str] = set()
        self.selected_node: Node = None

        self._setup_content()

        about = about_dialog(
            no_title_bar=True, no_background=True, tag=f"{self.tag}_about_popup"
        )
        dpg.set_frame_callback(dpg.get_frame_count() + 1, lambda: center_window(about))

    def notification(self, message: str, severity: int = logging.INFO) -> None:
        if severity < self.min_notification_severity:
            return

        lines = [
            subline for line in message.split("\n") for subline in textwrap.wrap(line)
        ]

        with dpg.mutex():
            with dpg.window(
                min_size=(20, 20),
                no_title_bar=True,
                no_focus_on_appearing=True,
                no_saved_settings=True,
                no_close=True,
                no_collapse=True,
                no_move=True,
                autosize=True,
            ) as note:
                for line in lines:
                    dpg.add_text(line, color=style.black)

            if severity >= logging.ERROR:
                theme = style.notification_error_theme
            elif severity >= logging.WARNING:
                theme = style.notification_warning_theme
            else:
                theme = style.notification_info_theme

            dpg.bind_item_theme(note, theme)

        dpg.split_frame(delay=64)

        w = dpg.get_item_width(note)
        h = dpg.get_item_height(note)
        pos = (
            dpg.get_viewport_width() - w - 50,
            dpg.get_viewport_height() - h - 50,
        )
        dpg.configure_item(note, pos=pos)

        def remove_notification():
            time.sleep(3.0)
            dpg.delete_item(note)

        Thread(target=remove_notification, daemon=True).start()

    def get_supported_file_extensions(self):
        return {
            "All supported files": ["*.xml", "*.hkx", "*.behbnd.dcx"],
            "Behavior XML": "*.xml",
            "Behavior HKX": "*.hkx",
            "DCX Binder": "*.behbnd.dcx",
        }

    def file_open(self):
        ret = open_file_dialog(
            default_dir=os.path.dirname(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self._do_load_from_file(ret)

    def _do_load_from_file(self, file_path: str):
        if not os.path.isfile(file_path):
            self.logger.error(f"File not found: {file_path}")
            self.config.remove_recent_file(file_path)
            self.config.save()

            self._regenerate_recent_files_menu()
            return

        if dpg.does_item_exist(f"{self.tag}_about_popup"):
            dpg.delete_item(f"{self.tag}_about_popup")

        self.logger.debug("======================================")
        self.logger.info("Loading file %s", file_path)

        with dpg.window(
            modal=True,
            no_close=True,
            no_move=True,
            no_collapse=True,
            no_title_bar=True,
            no_resize=True,
            no_scroll_with_mouse=True,
            no_scrollbar=True,
            no_saved_settings=True,
        ) as loading_screen:
            dpg.add_loading_indicator(color=style.yellow)
            dpg.add_text(f"Loading {os.path.basename(file_path)}")
            dpg.add_separator()
            dpg.add_text("Relax, get a coffee, breathe, maybe")
            dpg.add_text("contemplate your life choices...")

        # Already centered, this will make it worse somehow
        # dpg.split_frame(delay=64)
        # center_window(loading_screen)

        self.alias_manager.clear()
        self.clear_attributes()
        self.remove_all_pinned_objects()
        self.close_all_dialogs()

        try:
            if file_path.lower().endswith(".hkx"):
                self._locate_hklib()
                self.logger.info("Converting HKX to XML...")
                file_path = hkx_to_xml(file_path)

            elif file_path.lower().endswith(".behbnd.dcx"):
                self._locate_witchy()
                self._locate_hklib()
                self.logger.info("Opening binder...")
                file_path = unpack_binder(file_path)

            self.logger.info("Loading behavior...")
            self.beh = HavokBehavior(file_path, undo=True)

            self.config.add_recent_file(file_path)
            self.config.save()
            self._regenerate_recent_files_menu()

            # Fix anything that was amiss in previous versions
            fix_variable_defaults(self.beh)

            filename = os.path.basename(file_path)
            dpg.configure_viewport(0, title=f"HkbEditor - {filename}")

            self.loaded_file = file_path
            self.last_save = 0.0
            self.canvas.clear()
            self._update_roots()

            self._reload_templates()
            self._set_menus_enabled(True)

            dpg.focus_item(f"{self.tag}_roots_filter")
        except Exception as e:
            details = traceback.format_exception_only(e)
            self.logger.error(
                f"Loading behavior failed: {details[0]}\nSee log for details!"
            )
            raise e
        finally:
            dpg.delete_item(loading_screen)

    def file_save(self):
        self._do_write_to_file(self.loaded_file)
        self.last_save = time()

    def file_save_as(self) -> bool:
        ret = save_file_dialog(
            default_dir=os.path.dirname(self.loaded_file or ""),
            default_file=os.path.basename(self.loaded_file or ""),
            filetypes=self.get_supported_file_extensions(),
        )

        if ret:
            self._do_write_to_file(ret)
            self.loaded_file = ret
            self.last_save = time()
            return True

        return False

    def _do_write_to_file(self, file_path):
        if self._busy:
            return

        self._busy = True
        loading = common_loading_indicator("Saving")

        try:
            if self.config.save_backups:
                shutil.copy(self.beh.file, self.beh.file + ".bak")

            self.beh.save_to_file(file_path)
            self.logger.info(f"Saved to {file_path}")
        finally:
            dpg.delete_item(loading)
            self._busy = False

    def _locate_witchy(self) -> str:
        if not self.config.witchy_exe or not os.path.isfile(self.config.witchy_exe):
            witchy_exe = open_file_dialog(
                title="Locate WitchyBND.exe", filetypes={"WitchyBND": "WitchyBND.exe"}
            )
            if not witchy_exe:
                self.logger.error("WitchyBND is required for repacking behavior")

            self.config.witchy_exe = witchy_exe
            self.config.save()

        return self.config.witchy_exe

    def _locate_hklib(self) -> str:
        if not self.config.hklib_exe or not os.path.isfile(self.config.hklib_exe):
            hklib_exe = open_file_dialog(
                title="Locate HKLib.exe", filetypes={"HKLib": "HKLib.CLI.exe"}
            )
            if not hklib_exe:
                self.logger.error("HKLib is required for repacking behavior")

            self.config.hklib_exe = hklib_exe
            self.config.save()

        return self.config.hklib_exe

    def _reload_character(self) -> None:
        if self._busy:
            return

        self._busy = True
        chr = self.beh.get_character_id()
        loading = common_loading_indicator(f"Reloading {chr}...")

        try:
            if not self.chr_reloader:
                if ChrReloader:
                    game_config = detect_game_config()
                    self.chr_reloader = ChrReloader(game_config)
                else:
                    self.logger.error("ChrReloader is not available")
                    return

            self.chr_reloader.reload_character(chr)
        except Exception as e:
            self.logger.error(f"Reloading {chr} failed: {e}")
            self.chr_reloader = None
        finally:
            dpg.delete_item(loading)
            self._busy = False

    def _repack_binder(self) -> None:
        if self._busy:
            return

        self._busy = True

        # Locate external tools
        self._locate_witchy()
        self._locate_hklib()

        loading = common_loading_indicator("Repacking binder...")

        try:
            self.logger.info("Saving XML...")
            self.file_save()
            self.logger.info("Converting XML to HKX...")
            xml_to_hkx(self.beh.file)
            self.logger.info("Repacking Binder...")
            pack_binder(self.beh.file)
            self.logger.info("Done!")
        finally:
            dpg.delete_item(loading)
            self._busy = False

    def exit_app(self):
        with dpg.window(
            label="Exit?",
            modal=True,
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            if self.last_save == 0.0:
                dpg.add_text("You have not saved yet. Exit anyways?")
            else:
                dpg.add_text(
                    f"It has been {self.last_save:.0f}s since your last save. Exit?"
                )

            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_button(label="Exit", callback=dpg.stop_dearpygui)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item(wnd))

        dpg.split_frame()
        center_window(wnd)

    def undo(self) -> None:
        if self.beh.undo() is None:
            self.logger.info("Nothing to undo")
            return

        self.logger.debug("Undo")

        for oid in self.get_pinned_objects():
            if oid not in self.beh.objects:
                self.remove_pinned_object(oid)

        self.regenerate()
        self.attributes_widget.regenerate()

    def redo(self) -> None:
        if self.beh.redo() is None:
            self.logger.info("Nothing to redo")
            return

        self.logger.debug("Redo")

        self.regenerate()
        self.attributes_widget.regenerate()

    def create_app_menu(self):
        # File
        with dpg.menu(label="File"):
            dpg.add_menu_item(label="Open...", callback=self.file_open)
            dpg.add_menu(label="Recent files", tag=f"{self.tag}_menu_recent_files")
            dpg.add_separator()

            dpg.add_menu_item(
                label="Save",
                shortcut="ctrl-s",
                callback=self.file_save,
                enabled=False,
                tag=f"{self.tag}_menu_file_save",
            )
            dpg.add_menu_item(
                label="Save as...",
                shortcut="ctrl-shift-s",
                callback=self.file_save_as,
                enabled=False,
                tag=f"{self.tag}_menu_file_save_as",
            )
            dpg.add_menu_item(
                label="Update name ID files...",
                callback=self.open_update_name_ids_dialog,
                enabled=False,
                tag=f"{self.tag}_menu_file_update_name_ids",
            )
            dpg.add_separator()

            dpg.add_menu_item(
                label="Repack Binder",
                shortcut="f4",
                callback=self._repack_binder,
                enabled=False,
                tag=f"{self.tag}_menu_repack_binder",
            )
            dpg.add_menu_item(
                label="Force game reload",
                shortcut="f5",
                callback=self._reload_character,
                enabled=False,
                tag=f"{self.tag}_menu_reload_character",
            )

            dpg.add_separator()

            dpg.add_menu_item(
                label="Save layout as default", callback=self._save_app_layout
            )
            dpg.add_menu_item(
                label="Restore factory layout",
                callback=self._restore_default_app_layout,
            )

            dpg.add_separator()
            dpg.add_menu_item(label="Exit", shortcut="ctrl-q", callback=self.exit_app)

        dpg.add_separator()

        # Edit
        with dpg.menu(label="Edit", enabled=False, tag=f"{self.tag}_menu_edit"):
            dpg.add_menu_item(
                label="Undo",
                shortcut="ctrl-z",
                callback=self.undo,
            )
            dpg.add_menu_item(
                label="Redo",
                shortcut="ctrl-y",
                callback=self.redo,
            )

            dpg.add_separator()

            with dpg.menu(label="Aliases"):
                dpg.add_menu_item(
                    label="Load Bone Names...", callback=self.load_bone_names
                )

            dpg.add_separator()

            dpg.add_menu_item(label="Variables...", callback=self.open_variable_editor)
            dpg.add_menu_item(label="Events...", callback=self.open_event_editor)
            dpg.add_menu_item(
                label="Animations...", callback=self.open_animation_names_editor
            )

            dpg.add_separator()

            dpg.add_menu_item(label="Pin Lost Objects", callback=self.pin_lost_objects)

            dpg.add_menu_item(
                label="Find Object...",
                shortcut="ctrl-f",
                callback=self.open_search_dialog,
            )

        # Workflows
        with dpg.menu(
            label="Workflows", enabled=False, tag=f"{self.tag}_menu_workflows"
        ):
            dpg.add_menu_item(
                label="Create Object...",
                callback=self.open_create_object_dialog,
            )
            dpg.add_menu_item(
                label="Register Clip...", callback=self.open_register_clip_dialog
            )
            dpg.add_menu_item(
                label="Create CMSG...", callback=self.open_create_cmsg_dialog
            )

            dpg.add_separator()

            dpg.add_menu_item(
                label="Verify Behavior...",
                callback=self.verify_behavior,
            )

            dpg.add_separator()

            dpg.add_menu_item(
                label="Import Hierarchy...", callback=self.open_hierarchy_import_dialog
            )

        # Tools
        with dpg.menu(
                label="Tools", enabled=False, tag=f"{self.tag}_menu_tools"
        ):
            # TODO enable once https://github.com/hoffstadt/DearPyGui/issues/2374 is done
            #dpg.add_menu_item(
            #    label="Graph Map...",
            #    callback=lambda: self.open_graphmap_dialog(),
            #)

            dpg.add_menu_item(
                label="Event Listener...",
                callback=lambda: self.open_eventlistener_dialog(),
            )
            
            # TODO needs an overhaul, right now it's just wrong
            #dpg.add_menu_item(
            #    label="StateInfo Graph...",
            #    callback=lambda: self.open_stategraph_dialog(),
            #)

            dpg.add_menu_item(
                label="Mirror Skeleton...",
                callback=self.open_mirror_skeleton_dialog,
            )

        # Templates
        with dpg.menu(
            label="Templates", enabled=False, tag=f"{self.tag}_menu_templates"
        ):
            dpg.add_separator(tag=f"{self.tag}_menu_templates_bottom")
            dpg.add_menu_item(label="Reload Templates", callback=self._reload_templates)

        # Settings
        with dpg.menu(label="Settings", tag=f"{self.tag}_menu_settings"):
            dpg.add_menu_item(
                label="Invert Zoom",
                check=True,
                default_value=self.config.invert_zoom,
                callback=self._update_config,
                tag=f"{self.tag}_config_invert_zoom",
            )
            dpg.add_menu_item(
                label="Single Branch Mode",
                check=True,
                default_value=self.config.single_branch_mode,
                callback=self._update_config,
                tag=f"{self.tag}_config_single_branch_mode",
            )
            dpg.add_menu_item(
                label="Save Backups",
                check=True,
                default_value=self.config.save_backups,
                callback=self._update_config,
                tag=f"{self.tag}_config_save_backups",
            )

        dpg.add_separator()

        with dpg.menu(label="Help"):
            with dpg.menu(label="dearpygui"):
                dpg.add_menu_item(
                    label="About", callback=lambda: dpg.show_tool(dpg.mvTool_About)
                )
                dpg.add_menu_item(
                    label="Metrics", callback=lambda: dpg.show_tool(dpg.mvTool_Metrics)
                )
                dpg.add_menu_item(
                    label="Documentation",
                    callback=lambda: dpg.show_tool(dpg.mvTool_Doc),
                )
                dpg.add_menu_item(
                    label="Debug", callback=lambda: dpg.show_tool(dpg.mvTool_Debug)
                )
                dpg.add_menu_item(
                    label="Style Editor",
                    callback=lambda: dpg.show_tool(dpg.mvTool_Style),
                )
                dpg.add_menu_item(
                    label="Font Manager",
                    callback=lambda: dpg.show_tool(dpg.mvTool_Font),
                )
                dpg.add_menu_item(
                    label="Item Registry",
                    callback=lambda: dpg.show_tool(dpg.mvTool_ItemRegistry),
                )
                dpg.add_menu_item(
                    label="Stack Tool",
                    callback=lambda: dpg.show_tool(dpg.mvTool_Stack),
                )

            dpg.add_separator()

            dpg.add_menu_item(
                label="HowTo",
                callback=self.open_guide,
            )
            dpg.add_menu_item(
                label="About",
                callback=self.open_about_dialog,
            )

        self._regenerate_recent_files_menu()

    def _save_app_layout(self):
        path = get_custom_layout_path()
        dpg.save_init_file(path)
        self.logger.info(f"Saved custom layout to {path}")

    def _restore_default_app_layout(self):
        default_layout = get_default_layout_path()
        user_layout = get_custom_layout_path()

        if os.path.isfile(user_layout):
            shutil.move(get_custom_layout_path(), get_custom_layout_path() + ".old")

        # Replace the user layout with the default
        shutil.move(default_layout, user_layout)

        with dpg.window(
            label="Layout Restored",
            modal=True,
            autosize=True,
            min_size=(100, 50),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_text("Layout restored - restart to apply!")
            dpg.add_separator()
            dpg.add_button(label="Okay", callback=lambda: dpg.delete_item(wnd))

    def _update_config(self, sender: str) -> None:
        alias = dpg.get_item_alias(sender)
        key = alias[len(f"{self.tag}_config_") :]

        if not hasattr(self.config, key):
            raise ValueError(f"Unknown config key {key}")

        setattr(self.config, key, dpg.get_value(sender))
        self.config.save()

    def _regenerate_recent_files_menu(self) -> None:
        dpg.delete_item(f"{self.tag}_menu_recent_files", slot=1, children_only=True)
        # dpg.split_frame()

        def load_file(sender: str, app_data: Any, file_path: str) -> None:
            if self.beh:
                # A behavior is loaded, save before exiting?

                def save_and_load():
                    dpg.delete_item(dialog)
                    self.file_save()
                    self._do_load_from_file(file_path)

                def save_as_and_load():
                    dpg.delete_item(dialog)
                    if self.file_save_as():
                        self._do_load_from_file(file_path)

                def just_load():
                    dpg.delete_item(dialog)
                    self._do_load_from_file(file_path)

                with dpg.window(
                    label="Continue?",
                    modal=True,
                    no_saved_settings=True,
                    on_close=lambda: dpg.delete_item(dialog),
                ) as dialog:
                    dpg.add_text("Save current behavior first?")

                    dpg.add_separator()
                    dpg.add_spacer(height=5)

                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Save", callback=save_and_load)
                        dpg.add_button(label="Save as", callback=save_as_and_load)
                        dpg.add_text("|")
                        dpg.add_button(label="Just do it", callback=just_load)

                dpg.split_frame()
                center_window(dialog)
            else:
                self._do_load_from_file(file_path)

        for i in range(10):
            if i < len(self.config.recent_files):
                path = self.config.recent_files[i]

                parts = path.split(os.sep)
                short = parts[-1]
                parts = parts[:-1]

                for p in reversed(parts):
                    short = os.path.join(p, short)
                    if len(short) > 70:
                        short = os.path.join("...", short)
                        break

                dpg.add_menu_item(
                    label=short,
                    parent=f"{self.tag}_menu_recent_files",
                    callback=load_file,
                    user_data=path,
                )
            else:
                # We need to add menu item stubs, otherwise the additional items will mess up
                # the dearpygui layout
                dpg.add_menu_item(
                    parent=f"{self.tag}_menu_recent_files",
                    show=False,
                )

    def _reload_templates(self) -> None:
        menu = f"{self.tag}_menu_templates"
        dpg.delete_item(menu, children_only=True)

        templates = get_templates()

        for template_file, (categories, template) in templates.items():
            parent = menu
            path = ""
            for cat in categories:
                path += cat + "/"
                if not dpg.does_item_exist(f"{self.tag}_menu_templates_cat_{path}"):
                    parent = dpg.add_menu(
                        label=cat,
                        tag=f"{self.tag}_menu_templates_cat_{path}",
                        parent=parent,
                    )

            if path:
                parent = f"{self.tag}_menu_templates_cat_{path}"

            dpg.add_menu_item(
                label=template,
                callback=lambda s, a, u: self.open_apply_template_dialog(u),
                user_data=template_file,
                parent=parent,
            )

        dpg.add_separator(tag=f"{self.tag}_menu_templates_bottom", parent=menu)
        dpg.add_menu_item(
            label="Reload Templates", parent=menu, callback=self._reload_templates
        )

    def _on_key_press(self, sender, key: int) -> None:
        if dpg.is_key_down(dpg.mvKey_ModShift) and dpg.is_key_down(dpg.mvKey_ModCtrl):
            if key == dpg.mvKey_S:
                self.file_save_as()

        elif dpg.is_key_down(dpg.mvKey_ModCtrl):
            if key == dpg.mvKey_S:
                self.file_save()
            elif key == dpg.mvKey_Q:
                self.exit_app()
            elif key == dpg.mvKey_Z:
                self.undo()
            elif key == dpg.mvKey_Y:
                self.redo()
            elif key == dpg.mvKey_F:
                self.open_search_dialog()

        elif dpg.is_key_down(dpg.mvKey_ModShift):
            pass

        else:
            if key == dpg.mvKey_F4:
                self._repack_binder()
            elif key == dpg.mvKey_F5:
                self._reload_character()

    def _set_menus_enabled(self, enabled: bool) -> None:
        func = dpg.enable_item if enabled else dpg.disable_item
        func(f"{self.tag}_menu_file_save")
        func(f"{self.tag}_menu_file_save_as")
        func(f"{self.tag}_menu_file_update_name_ids")
        func(f"{self.tag}_menu_repack_binder")
        func(f"{self.tag}_menu_reload_character")
        func(f"{self.tag}_menu_edit")
        func(f"{self.tag}_menu_workflows")
        func(f"{self.tag}_menu_tools")
        func(f"{self.tag}_menu_templates")

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_None, callback=self._on_key_press)

    def _on_resize(self):
        cw, ch = dpg.get_item_rect_size(f"{self.tag}_canvas_window")
        dpg.set_item_width(self.canvas.tag, cw)
        dpg.set_item_height(self.canvas.tag, ch)

    def _setup_content(self) -> None:
        with dpg.viewport_menu_bar():
            self.create_app_menu()

        # Roots
        with dpg.window(
            label="Root Nodes",
            autosize=True,
            no_close=True,
            no_scrollbar=True,
            tag=f"{self.tag}_roots_window",
        ):
            dpg.add_input_text(
                hint="Filter",
                callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                user_data=f"{self.tag}_roots_table",
                tag=f"{self.tag}_roots_filter",
                width=-1,
            )
            dpg.add_separator()
            # Tables are more flexible with item design and support filtering
            with dpg.table(
                delay_search=True,
                no_host_extendX=True,
                header_row=False,
                # policy=dpg.mvTable_SizingFixedFit,
                scrollY=True,
                tag=f"{self.tag}_roots_table",
            ) as self.roots_table:
                dpg.add_table_column(label="Name")

        # Canvas
        with dpg.window(
            label="Graph",
            autosize=True,
            no_close=True,
            no_scrollbar=True,
            tag=f"{self.tag}_canvas_window",
        ):
            self.canvas = GraphWidget(
                None,
                GraphLayout(),
                on_node_selected=self.on_node_selected,
                node_menu_func=self.open_node_menu,
                get_node_frontpage=self.get_node_frontpage,
                tag=f"{self.tag}_canvas",
            )

        # Attributes panel
        with dpg.window(
            label="Attributes",
            autosize=True,
            no_close=True,
            no_scrollbar=True,
            tag=f"{self.tag}_attributes_window",
        ):
            dpg.add_input_text(
                hint="Filter",
                tag=f"{self.tag}_attribute_filter",
                callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)),
                user_data=None,  # see below
                width=-1,
            )
            dpg.add_separator()

            # Child window is needed to fix table sizing
            with dpg.child_window(border=False):
                self.attributes_widget = AttributesWidget(
                    self.alias_manager,
                    jump_callback=self.jump_to_object,
                    search_attribute_callback=self.search_attribute,
                    on_graph_changed=self.regenerate,
                    on_value_changed=self._on_value_modified,
                    pin_object_callback=self.add_pinned_object,
                    get_pinned_objects_callback=self.get_pinned_objects,
                    tag=f"{self.tag}_attributes_widget",
                )

        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_frame_callback(2, self._on_resize)

        # Update the input box for filtering the table
        self.attributes_table = self.attributes_widget._attributes_table
        dpg.set_item_user_data(f"{self.tag}_attribute_filter", self.attributes_table)

        # Pinned objects
        with dpg.window(
            label="Pinned Objects",
            autosize=True,
            no_close=True,
            no_scroll_with_mouse=True,
            no_scrollbar=True,
            tag=f"{self.tag}_pinned_objects",
        ):
            # Child window to fix table sizing
            with dpg.child_window(border=False):
                with dpg.table(
                    no_host_extendX=True,
                    resizable=True,
                    borders_innerV=True,
                    policy=dpg.mvTable_SizingFixedFit,
                    scrollY=True,
                    tag=f"{self.tag}_pinned_objects_table",
                ) as self.pinned_objects_table:
                    dpg.add_table_column(label="ID", width_stretch=True)
                    dpg.add_table_column(label="Name", width_stretch=True)
                    dpg.add_table_column(label="Type", width_stretch=True)

        with dpg.item_handler_registry(tag=f"{self.tag}_pin_registry"):
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Left, callback=self.show_pin_attributes
            )
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Right, callback=self.open_pin_menu
            )

    def _on_root_selected(self, sender: str, selected: bool, root_id: str):
        # NOTE for now we don't allow deselecting SMs
        selected = True
        dpg.set_value(f"{self.tag}_root_{root_id}_selectable", True)

        # Rebuild the graph even if the root_id is already selected
        self.canvas.clear()
        self.clear_attributes()
        self.selected_node = None

        # For now we only allow one root to be selected
        for other in self.get_root_ids():
            self.selected_roots.discard(other)
            tag = f"{self.tag}_root_{other}_selectable"
            if other != root_id and dpg.does_item_exist(tag):
                dpg.set_value(tag, False)

        if selected:
            self.selected_roots.add(root_id)
            graph: nx.DiGraph = self.get_graph(root_id)
            self.canvas.set_graph(graph)
        else:
            if root_id in self.selected_roots:
                self.selected_roots.remove(root_id)
            self.canvas.set_graph(None)

    def _update_roots(self) -> None:
        dpg.delete_item(self.roots_table, children_only=True, slot=1)

        # Columns will be hidden if header_row=False and no rows exist initially
        for col in dpg.get_item_children(self.roots_table, slot=0):
            dpg.show_item(col)

        root_ids = self.get_root_ids()
        for root_id in root_ids:
            label = self.get_node_frontpage_short(root_id)
            with dpg.table_row(filter_key=label, parent=self.roots_table):
                dpg.add_selectable(
                    label=label,
                    user_data=root_id,
                    callback=self._on_root_selected,
                    tag=f"{self.tag}_root_{root_id}_selectable",
                )

    def get_pinned_objects(self) -> list[str]:
        ret = []

        for row in dpg.get_item_children(f"{self.tag}_pinned_objects_table", slot=1):
            ret.append(dpg.get_item_user_data(row))

        return ret

    def add_pinned_object(self, object_id: HkbRecord | str) -> None:
        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        if dpg.does_item_exist(f"{self.tag}_pin_{object_id}"):
            # Already pinned
            return

        obj = self.beh.objects[object_id]

        def on_select(sender: str):
            # No selection
            dpg.set_value(sender, False)

        with dpg.table_row(
            # For some reason self.pinned_objects_table doesn't work?
            parent=f"{self.tag}_pinned_objects_table",
            tag=f"{self.tag}_pin_{object_id}",
            user_data=object_id,
        ):
            dpg.add_selectable(
                label=object_id,
                span_columns=True,
                callback=on_select,
                user_data=object_id,
            )
            dpg.bind_item_handler_registry(dpg.last_item(), f"{self.tag}_pin_registry")
            dpg.add_text(
                obj.get_field("name", None, resolve=True),
            )
            dpg.add_text(obj.type_name)

    def remove_pinned_object(self, object_id: str) -> None:
        for row in dpg.get_item_children(f"{self.tag}_pinned_objects_table", slot=1):
            if dpg.get_item_user_data(row) == object_id:
                dpg.delete_item(row)
                break

    def remove_all_pinned_objects(self) -> None:
        dpg.delete_item(f"{self.tag}_pinned_objects_table", children_only=True, slot=1)

    def pin_lost_objects(self) -> None:
        for oid in self.find_lost_objects():
            self.add_pinned_object(oid)

    def show_pin_attributes(self, sender: str, app_data: str, user_data: Any) -> None:
        _, selectable = app_data
        object_id = dpg.get_item_user_data(selectable)
        pinned_obj: HkbRecord = self.beh.retrieve_object(object_id)

        self.canvas.deselect()
        self.attributes_widget.set_record(pinned_obj)

    def open_pin_menu(self, sender: str, app_data: str, user_data: Any) -> None:
        _, selectable = app_data
        object_id = dpg.get_item_user_data(selectable)
        pinned_obj: HkbRecord = self.beh.retrieve_object(object_id)

        # Pin context menu
        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_saved_settings=True,
            autosize=True,
        ) as popup:
            dpg.add_selectable(
                label="Unpin",
                callback=lambda s, a, u: self.remove_pinned_object(u),
                user_data=object_id,
            )
            dpg.add_selectable(
                label="Unpin All",
                callback=self.remove_all_pinned_objects,
            )
            dpg.add_selectable(
                label="Jump To",
                callback=lambda s, a, u: self.jump_to_object(u),
                user_data=object_id,
            )
            make_copy_menu(pinned_obj)

        dpg.set_item_pos(popup, dpg.get_mouse_pos(local=False))

    def get_root_ids(self) -> list[str]:
        sm_type = self.beh.type_registry.find_first_type_by_name("hkbStateMachine")
        roots = [
            (obj["name"].get_value(), obj.object_id)
            for obj in self.beh.find_objects_by_type(sm_type)
        ]
        # Names for sorting, but return root IDs. They'll be resolved to names via
        # get_node_frontpage_short
        return [r[1] for r in sorted(roots)]

    def get_graph(self, root_id: str) -> nx.DiGraph:
        return self.beh.build_graph(root_id)

    def get_node_frontpage(self, node: Node | str) -> list[str]:
        if isinstance(node, Node):
            node = node.id
        
        obj = self.beh.objects[node]

        lines = [
            (obj.type_name, style.white),
            (node, style.blue),
        ]

        # Check if there is an event associated with this StateInfo
        name = obj.get_field("name", None, resolve=True)
        
        if obj.type_name == "hkbStateMachine::StateInfo":
            name = f"{name} ({obj['stateId'].get_value()})"

            sm = self.beh.objects[self.canvas.root]
            transitions: HkbArray[HkbRecord] = sm.get_field(
                "wildcardTransitions/transitions", None
            )
            # Not all statemachines have wildcard transitions (just root maybe?)
            if transitions:
                state_id = obj["stateId"].get_value()
                for trans in transitions:
                    if trans["toStateId"].get_value() == state_id:
                        event_id = trans["eventId"].get_value()
                        if event_id >= 0:
                            event = self.beh.get_event(event_id)
                            lines.insert(0, (f"<{event}>", style.green))

                        break

        if name:
            lines.insert(0, (name, style.yellow))

        return lines

    def get_node_frontpage_short(self, node_id: str) -> str:
        return self.beh.objects[node_id]["name"].get_value()

    def on_node_selected(self, node: Node | str) -> None:
        self.selected_node = node

        # Update the attributes panel
        if node:
            self._update_attributes(node)
        else:
            self.clear_attributes()
    
    def _create_attach_menu(self, node: Node):

        def get_target_type_id(obj: XmlValueHandler):
            if isinstance(obj, HkbPointer):
                return obj.subtype_id

            if isinstance(obj, HkbArray) and obj.is_pointer_array:
                return self.beh.type_registry.get_subtype(obj.element_type_id)

            raise ValueError(f"Expected HkbPointer or HkbArray, got {obj}")

        def do_attach(target_obj: XmlValueHandler, new_obj: HkbRecord) -> HkbPointer:
            if isinstance(target_obj, HkbPointer):
                target_obj.set_value(new_obj)
            elif isinstance(target_obj, HkbArray):
                target_obj.append(new_obj)
            else:
                raise ValueError(f"Invalid target object {target_obj}")

            self.logger.info(f"Attached {new_obj} to {target_obj}")

            self.regenerate()
            canvas_node = self.canvas.nodes[new_obj.object_id]
            self.on_node_selected(canvas_node)

        def attach_new_object(
            sender: str, app_data: str, target: tuple[HkbRecord, str]
        ):
            target_obj = target[0].get_field(target[1])
            target_type_id = get_target_type_id(target_obj)

            create_object_dialog(
                self.beh,
                self.alias_manager,
                lambda s, new_obj, target_obj: do_attach(target_obj, new_obj),
                allowed_types=[target_type_id],
                include_derived_types=True,
                selected_type_id=target_type_id,
                user_data=target_obj,
                tag=f"{self.tag}_attach_new_object_{node.id}_{path}",
            )

        def attach_from_xml(sender: str, app_data: str, target: tuple[HkbRecord, str]):
            target_obj = target[0].get_field(target[1])

            try:
                xml = xml_from_str(pyperclip.paste())
                xml_type_id = xml.get("typeid")
            except Exception:
                raise ValueError("Clipboard does not contain valid XML data")

            with self.beh.transaction():
                new_obj = HkbRecord.init_from_xml(self.beh, xml_type_id, xml)
                self.beh.add_object(new_obj, self.beh.new_id())

                do_attach(target_obj, new_obj)

        def attach_hierarchy(
            sender: str,
            app_data: str,
            target: tuple[HkbRecord, str],
            children_only: bool = False,
        ):
            target_obj, target_path = target
            xml = pyperclip.paste()

            def on_merge_success(result):
                new_objects = [
                    r.result
                    for r in result.objects.values()
                    if r.action == MergeAction.NEW
                ]
                self.logger.info(
                    f"Attached hierarchy of {len(new_objects)} elements to {target_obj.object_id}/{target_path}"
                )

                if result.pin_objects:
                    for obj in new_objects:
                        self.add_pinned_object(obj)

                self.regenerate()

            if children_only:
                paste_children(self.beh, xml, target_obj, target_path, on_merge_success)
            else:
                paste_hierarchy(
                    self.beh, xml, target_obj, target_path, on_merge_success
                )

        def attach_children(sender: str, app_data: str, target: tuple[HkbRecord, str]):
            attach_hierarchy(sender, app_data, target, True)

        def add_attach_menu_items(node: Node, path: str, obj: XmlValueHandler):
            record = self.beh.objects[node.id]
            label = path
            if isinstance(obj, HkbArray):
                label += " <array>"

            with dpg.menu(label=label):
                dpg.add_selectable(
                    label="New Object",
                    callback=attach_new_object,
                    user_data=(record, path),
                )
                dpg.add_selectable(
                    label="New from XML",
                    callback=attach_from_xml,
                    user_data=(record, path),
                )

                if isinstance(obj, HkbArray):
                    dpg.add_selectable(
                        label="Hierarchy (full)",
                        callback=attach_hierarchy,
                        user_data=(record, path),
                    )

                    dpg.add_selectable(
                        label="Hierarchy (children only)",
                        callback=attach_children,
                        user_data=(record, path),
                    )
                else:
                    dpg.add_selectable(
                        label="Hierarchy",
                        callback=attach_hierarchy,
                        user_data=(record, path),
                    )

        with dpg.menu(label="Attach"):
            obj = self.beh.objects[node.id]

            # Pointers
            ptr: HkbPointer
            for path, ptr in obj.find_fields_by_type(HkbPointer):
                if ":" in path.rsplit("/", maxsplit=1)[-1]:
                    # A path like abc/def:0 means we found a pointer inside a pointer array
                    continue

                add_attach_menu_items(node, path, ptr)

            dpg.add_separator()

            # Arrays
            array: HkbArray
            for path, array in obj.find_fields_by_type(HkbArray):
                if array.is_pointer_array:
                    add_attach_menu_items(node, path, array)

    def open_node_menu(self, node: Node):
        obj = self.beh.objects.get(node.id)
        if not obj:
            return []

        with dpg.window(
            popup=True,
            min_size=(100, 20),
            no_saved_settings=True,
            on_close=lambda: dpg.delete_item(wnd),
        ) as wnd:
            dpg.add_text(node.id, color=style.blue)
            dpg.add_separator()

            # Copy & attach menus
            dpg.add_selectable(
                label="Insert Selector",
                callback=lambda s, a, u: self._insert_selector(u),
                user_data=node,
            )

            make_copy_menu(obj)
            self._create_attach_menu(node)

            with dpg.menu(label="Delete"):
                dpg.add_selectable(
                    label="Subtree",
                    callback=lambda s, a, u: self._delete_node_cascade(u),
                    user_data=node,
                )
                dpg.add_selectable(
                    label="Single node",
                    callback=lambda s, a, u: self._delete_node(u),
                    user_data=node,
                )

            dpg.add_separator()

            dpg.add_selectable(
                label="Search children",
                callback=lambda s, a, u: self.open_search_dialog(f"parent={node.id}"),
                user_data=node,
            )
            dpg.add_selectable(
                label="Pin Object",
                callback=lambda s, a, u: self.add_pinned_object(u),
                user_data=obj,
            )

    def _insert_selector(self, node: Node) -> None:
        parent = next(self.canvas.graph.predecessors(node.id), None)
        if not parent:
            self.logger.warning("Node has no parent in current graph")
            return

        parent_record = self.beh.objects[parent]
        parent_ptr: HkbPointer
        for _, parent_ptr in parent_record.find_fields_by_type(HkbPointer):
            if parent_ptr.get_value() == node.id:
                target = parent_ptr.get_target()
                break
        else:
            self.logger.warning("Could not locate child node in parent")
            return

        msg_type = self.beh.type_registry.find_first_type_by_name("hkbManualSelectorGenerator")
        if msg_type not in self.beh.type_registry.get_compatible_types(parent_ptr.subtype_id):
            self.logger.warning("Parent pointer is incompatible with hkbManualSelectorGenerator")
            return

        def on_object_created(sender: str, selector: HkbRecord, user_data: Any):
            with self.beh.transaction():
                selector["generators"].append(target)
                parent_ptr.set_value(selector)

            # This is a bit ugly, but so is adding more stuff to new_object
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(selector.object_id)

            self.regenerate()

        create_object_dialog(
            self.beh,
            self.alias_manager,
            on_object_created,
            allowed_types=[msg_type],
            include_derived_types=True,
            selected_type_id=msg_type,
            title="Insert Selector",
        )

    def _delete_node(self, node: Node) -> None:
        record = self.beh.objects.get(node.id)
        if not record:
            return

        self.logger.info(f"Deleting single node {node.id}")
        with self.beh.transaction():
            self._on_node_delete(node.id)

            # Delete the object last so that any code running before can still inspect it
            self.beh.delete_object(record.object_id)

        self.regenerate()

    def _delete_node_cascade(self, node: Node) -> None:
        record = self.beh.objects.get(node.id)
        if not record:
            return

        root_graph = self.beh.root_graph()
        node_graph = self.beh.build_graph(node.id)

        delete_list: list[str] = []
        children = set(nx.descendants(root_graph, node.id))
        for child, in_degree in root_graph.in_degree(children):
            # Ignore any in-edges from parents in the node's subtree
            for parent in root_graph.predecessors(child):
                if parent in node_graph:
                    in_degree -= 1

            if in_degree == 0:
                delete_list.append(child)

        self.logger.info(
            f"Deleting {len(delete_list)} descendants of node {node.id} with no other parents"
        )
        with self.beh.transaction():
            self._on_node_delete(node.id)

            self.beh.delete_object(node.id)
            for child in delete_list:
                self.beh.delete_object(child)

        self.regenerate()

    def _on_node_delete(self, object_id: str) -> None:
        obj = self.beh.objects[object_id]
        if obj.type_name == "hkbStateMachine::StateInfo":
            self._on_stateinfo_removed(object_id)

        # Update any pointers that are referencing the deleted object. We could use
        # HavokBehavior.find_referees, but using the graph is much more efficient
        first_parent = None
        for parent_id in self.canvas.graph.predecessors(object_id):
            if not first_parent:
                first_parent = parent_id

            parent = self.beh.objects[parent_id]
            for path, ptr in parent.find_fields_by_type(HkbPointer):
                if ptr.get_value() == object_id:
                    index_match = re.match(r"^(.*):([0-9]+)$", path)
                    if index_match:
                        # Pointer belongs to a pointer array remove this index
                        index = int(index_match.group(2))
                        array: HkbArray = parent.get_field(index_match.group(1))
                        array.pop(index)
                    else:
                        # Regular field
                        ptr.set_value(None)

        if first_parent:
            self.selected_node = self.canvas.nodes[first_parent]

    def _on_stateinfo_removed(self, stateinfo_id: str) -> None:
        stateinfo = self.beh.objects[stateinfo_id]
        state_id = stateinfo["stateId"].get_value()

        target_sm_id = next(self.canvas.graph.predecessors(stateinfo_id))
        target_sm = self.beh.objects[target_sm_id]

        transition_info = target_sm["wildcardTransitions"].get_target()
        transitions: HkbArray = transition_info["transitions"]

        for idx, trans in enumerate(transitions):
            if trans["toStateId"].get_value() == state_id:
                transitions.pop(idx)
                self.logger.info(
                    f"Deleted obsolete wildcard transition {idx} for state {state_id}"
                )
                break

    def _copy_to_clipboard(self, data: str) -> None:
        try:
            pyperclip.copy(data)
            self.logger.info("Copied to clipboard")
        except Exception as e:
            self.logger.warning(f"Copying value failed: {e}", exc_info=e)

    def _on_value_modified(
        self,
        sender,
        handler: XmlValueHandler,
        change: tuple[Any, Any],
    ) -> None:
        old_value, new_value = change

        if isinstance(handler, HkbPointer):
            if old_value:
                oid = (
                    old_value.object_id
                    if isinstance(old_value, HkbRecord)
                    else old_value
                )

                if oid in self.beh.objects:
                    # Could be an entirely new pointer object with no previous value
                    self.add_pinned_object(old_value)
                    self.logger.info("Pinned previous object %s", old_value)

            # If a StateInfo pointer was removed from a statemachine we need to clean up
            # the wildcard transitions
            if (
                old_value
                and new_value is None
                and handler.subtype_name == "hkbStateMachine::StateInfo"
            ):
                old_id = (
                    old_value.object_id
                    if isinstance(old_value, HkbRecord)
                    else old_value
                )
                self._on_stateinfo_removed(old_id)

    def _update_attributes(self, node):
        record = self.beh.objects[node.id]
        self.attributes_widget.set_record(record)

    def regenerate(self) -> None:
        sm = self.get_active_statemachine()

        if not sm:
            # No active statemachine yet
            self.canvas.clear()
            self.attributes_widget.clear()
            return
        
        root_id = sm.object_id
        self.canvas.set_graph(self.get_graph(root_id))

        selected = self.selected_node
        if selected and selected.id in self.canvas.graph:
            # Will lead to on_node_selected, which regenerates the attributes widget
            # TODO this is a mess, merge base_editor with this class
            self.canvas.select(selected)
        else:
            self.attributes_widget.clear()

    def clear_attributes(self):
        self.attributes_widget.clear()

    # Common use cases
    def get_active_statemachine(self, for_object_id: str = None) -> HkbRecord:
        if not for_object_id:
            if self.canvas.graph:
                for_object_id = self.canvas.root
            elif self.selected_node:
                for_object_id = self.selected_node.id

        if not for_object_id:
            return None

        sm_type = self.beh.type_registry.find_first_type_by_name("hkbStateMachine")
        obj = self.beh.objects[for_object_id]
        if obj.type_id == sm_type:
            return obj

        return next(
            (sm for sm in self.beh.find_hierarchy_parents_for(for_object_id, sm_type)),
            None,
        )

    def find_lost_objects(self) -> list[str]:
        graph = self.beh.build_graph(self.beh.root_sm.object_id)
        lost = [n for n in self.beh.objects.keys() if n not in graph]
        return lost

    # Not used right now, but might be useful at some point
    def get_active_cmsg(self) -> HkbRecord:
        if self.selected_node:
            candidates = [self.selected_node.id]
            cmsg_type = self.beh.type_registry.find_first_type_by_name(
                "CustomManualSelectorGenerator"
            )

            while candidates:
                oid = candidates.pop()
                obj = self.beh.objects[oid]
                if obj.type_id == cmsg_type:
                    return obj

                candidates.extend(self.canvas.graph.predecessors(oid))

        return None

    def jump_to_object(self, object_id: str):
        if isinstance(object_id, HkbRecord):
            object_id = object_id.object_id

        root = self.get_active_statemachine()
        if root:
            # Check if the object is in the already active state machine first
            if not next(self.beh.query(object_id, search_root=root), None):
                root = None

        if not root:
            # Find the (first) statemachine the object appears in
            root = self.get_active_statemachine(object_id)

            if not root:
                self.logger.info("Object %s is not part of any statemachine", object_id)
                return

            self._on_root_selected("", True, root.object_id)

        # Reveal the node in the state machine graph
        path = nx.shortest_path(self.canvas.graph, root.object_id, object_id)
        self.clear_attributes()
        self.canvas.show_node_path(path)
        self.canvas.look_at_node(object_id)
    
    def search_attribute(self, path: str, value: XmlValueHandler):
        path = re.sub(r":[0-9]+", ":*", path)
        self.open_search_dialog(f"{path}={value.get_value()}")

    ####
    # Dialogs
    ####

    def open_update_name_ids_dialog(self):
        tag = f"{self.tag}_update_name_ids_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        update_name_ids_dialog(self.beh, tag=tag)

    def open_variable_editor(self):
        tag = f"{self.tag}_edit_variables_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: list):
            if self.beh.find_variable(new_value[0], None) is not None:
                raise ValueError(
                    "A variable named '%s' already exists (%d)", new_value[0], idx
                )

            try:
                new_value[4] = literal_eval(new_value[4])
            except Exception:
                # Assume it's actually a string
                pass

            self.beh.create_variable(*new_value, idx)

            # Update new_value from the created variable
            new_value[:] = self.beh.get_variable(idx).astuple()

            if idx not in (-1, len(self.beh._variables) - 1):
                self.logger.info("Fixing affected references of known variable attributes")
                fix_index_references(self.beh, variable_attributes, None, idx)

        def on_update(
            idx: int,
            old_value: tuple[str, VariableType, int, int, str],
            new_value: tuple[str, VariableType, int, int, str],
        ):
            new_value = list(new_value)
            try:
                new_value[4] = literal_eval(new_value[4])
            except Exception:
                # Assume it's actually a string
                pass

            self.beh.delete_variable(idx)
            self.beh.create_variable(*new_value, idx=idx)

        def on_delete(idx: int):
            self.beh.delete_variable(idx)
            if idx not in (-1, len(self.beh._variables) + 1):
                self.logger.info("Fixing affected references of known variable attributes")
                fix_index_references(self.beh, variable_attributes, idx, None)

        def on_move(idx: int, new_idx: int):
            self.beh.move_variable(idx, new_idx)
            self.logger.info("Fixing affected references of known variable attributes")
            fix_index_references(self.beh, variable_attributes, idx, new_idx)

        edit_simple_array_dialog(
            [
                (v.name, v.vtype.value, v.vmin, v.vmax, str(v.default))
                for v in self.beh.get_variables(full_info=True)
            ],
            {"Name": str, "Type": VariableType, "Min": int, "Max": int, "Default": str},
            title="Edit Variables",
            help="""\
                NOTE that variables are referenced by their index in bindings and TAE. HkbEditor will adjust references in common record types, but may miss newer or more obscure ones.
                
                Remember to run "File/Update name ID Files" after adding new entries!
                """,
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            on_move=on_move,
            tag=tag,
        )

    def open_event_editor(self):
        tag = f"{self.tag}_edit_events_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: list):
            new_value = new_value[0]
            if self.beh.find_event(new_value, None) is not None:
                raise ValueError(
                    "An event named '%s' already exists (%d)", new_value, idx
                )

            self.beh.create_event(new_value, idx)
            if idx not in (-1, len(self.beh._events) - 1):
                self.logger.info("Fixing affected references of known event attributes")
                fix_index_references(self.beh, event_attributes, None, idx)

        def on_update(idx: int, old_value: tuple[str], new_value: list):
            old_value = old_value[0]
            new_value = new_value[0]

            self.beh.delete_event(idx)
            self.beh.create_event(new_value, idx=idx)

        def on_delete(idx: int):
            self.beh.delete_event(idx)
            if idx not in (-1, len(self.beh._events) + 1):
                self.logger.info("Fixing affected references of known event attributes")
                fix_index_references(self.beh, event_attributes, idx, None)

        def on_move(idx: int, new_idx: int):
            self.beh.move_event(idx, new_idx)
            self.logger.info("Fixing affected references of known event attributes")
            fix_index_references(self.beh, event_attributes, idx, new_idx)

        edit_simple_array_dialog(
            [(e,) for e in self.beh.get_events()],
            {"Name": str},
            title="Edit Events",
            help="""\
                NOTE that events are referenced by their index in TransitionInfos and other nodes. HkbEditor will adjust references in common record types, but may miss newer or more obscure ones.
                
                Remember to run "File/Update name ID Files" after adding new entries!
                """,
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            on_move=on_move,
            tag=tag,
        )

    def open_animation_names_editor(self):
        tag = f"{self.tag}_edit_animation_names_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_add(idx: int, new_value: list):
            new_value = new_value[0]
            if self.beh.find_animation(new_value, None) is not None:
                raise ValueError(
                    "An animation named '%s' already exists (%d)", new_value, idx
                )

            self.beh.create_animation(new_value, idx)
            if idx not in (-1, len(self.beh._animations) - 1):
                self.logger.info("Fixing affected references of known animation attributes")
                fix_index_references(self.beh, animation_attributes, None, idx)

        def on_update(idx: int, old_value: tuple[str], new_value: list):
            old_value = old_value[0]
            new_value = new_value[0]

            self.beh.delete_animation(idx)
            self.beh.create_animation(new_value, idx=idx)

        def on_delete(idx: int):
            self.beh.delete_animation(idx)
            if idx not in (-1, len(self.beh._animations) + 1):
                self.logger.info("Fixing affected references of known animation attributes")
                fix_index_references(self.beh, animation_attributes, idx, None)

        def on_move(idx: int, new_idx: int):
            self.beh.move_animation(idx, new_idx)
            self.logger.info("Fixing affected references of known animation attributes")
            fix_index_references(self.beh, animation_attributes, idx, new_idx)

        edit_simple_array_dialog(
            [(a,) for a in self.beh.get_animations()],
            {"Name": str},
            title="Edit Animation Names",
            help="""\
                NOTE that events are referenced by their index in ClipGenerators. HkbEditor will adjust references in common record types, but may miss newer or more obscure ones.
                """,
            on_add=on_add,
            on_update=on_update,
            on_delete=on_delete,
            on_move=on_move,
            tag=tag,
        )

    def open_search_dialog(self, query: str = ""):
        tag = f"{self.tag}_search_dialog"
        if dpg.does_item_exist(tag):
            if query:
                # Open a new dialog replacing the previous search
                dpg.delete_item(tag)
                dpg.split_frame()
            else:
                dpg.show_item(tag)
                dpg.focus_item(tag)
                return

        def on_results(sender: str, matches: list[HkbRecord], user_data: Any) -> None:
            self.canvas.clear_highlights()
            for obj in matches:
                self.canvas.set_highlight(obj.object_id, True, color=style.red)

        search_objects_dialog(
            self.beh,
            pin_callback=lambda s, a, u: self.add_pinned_object(a),
            jump_callback=lambda s, a, u: self.jump_to_object(a),
            initial_filter=query,
            result_callback=on_results,
            tag=tag,
        )

    def open_graphmap_dialog(self):
        tag = f"{self.tag}_graphmap_dialog"
        if dpg.does_item_exist(tag):
            # TODO just for testing
            graphmap: GraphMap = dpg.get_item_user_data(tag)
            graphmap.set_graph(self.canvas.graph)
            dpg.show_item(tag)
            #dpg.focus_item(tag)
            return

        def on_graphnode_selected(node_id: str):
            # TODO is this what we want?
            self.jump_to_object(node_id)

        with dpg.window(
            width=500, 
            height=500,
            # FIXME crashes on close
            on_close=lambda: dpg.delete_item(dialog),
            tag=tag,
        ) as dialog:
            g = self.canvas.graph
            w = GraphMap(
                g, 
                self.get_node_frontpage, 
                on_graphnode_selected,
                tag + "_content"
            )

        dpg.set_item_user_data(dialog, w)


    def open_eventlistener_dialog(self):
        tag = f"{self.tag}_event_listener_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        eventlistener_dialog(tag=tag)

    def open_stategraph_dialog(self):
        tag = f"{self.tag}_state_graph_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        active_sm = self.get_active_statemachine()
        open_state_graph_viewer(
            self.beh,
            active_sm.object_id if active_sm else None,
            jump_callback=lambda s, a, u: self.jump_to_object(a.object_id),
            tag=tag,
        )

    def open_create_object_dialog(self):
        tag = f"{self.tag}_create_object_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_object_created(sender: str, new_object: HkbRecord, user_data: Any):
            # This is a bit ugly, but so is adding more stuff to new_object
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(new_object.object_id)

        create_object_dialog(
            self.beh,
            self.alias_manager,
            on_object_created,
            tag=tag,
        )

    def open_register_clip_dialog(self):
        tag = f"{self.tag}_register_clip_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_clip_registered(
            sender: str, records: tuple[HkbRecord, HkbRecord], user_data: Any
        ):
            cmsg, clip = records

            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(cmsg)
                self.add_pinned_object(clip)

            self.jump_to_object(clip)

        register_clip_dialog(
            self.beh,
            on_clip_registered,
            tag=tag,
        )

    def open_create_cmsg_dialog(self):
        tag = f"{self.tag}_create_cmsg_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_cmsg_created(
            sender: str,
            records: tuple[HkbRecord, HkbRecord, HkbRecord],
            user_data: Any,
        ):
            stateinfo, cmsg, clip = records

            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                self.add_pinned_object(stateinfo)
                self.add_pinned_object(cmsg)
                self.add_pinned_object(clip)

            # Not sure why this is required here, but not for register_clip above
            self.regenerate()
            self.jump_to_object(cmsg)

        active_sm = self.get_active_statemachine()
        create_cmsg_dialog(
            self.beh,
            on_cmsg_created,
            active_statemachine_id=active_sm.object_id if active_sm else None,
            tag=tag,
        )

    def load_bone_names(self) -> None:
        self.loaded_skeleton_path = None

        file_path = open_file_dialog(
            title="Select Skeleton", filetypes={"Skeleton files": "*.xml"}
        )

        if not file_path:
            return

        try:
            self.logger.info("Loading bone names from %s", file_path)

            bones = load_skeleton_bones(file_path)
            self.loaded_skeleton_path = file_path

            boneweights_type_id = self.beh.type_registry.find_first_type_by_name(
                "hkbBoneWeightArray"
            )
            basepath = "boneWeights"
            aliases = AliasMap()

            for idx, bone in enumerate(bones):
                aliases.add(bone, f"{basepath}:{idx}", boneweights_type_id, None)

            # Insert left so that these aliases take priority
            self.alias_manager.aliases.insert(0, aliases)
        except ValueError as e:
            self.logger.error("Loading bone names failed: %s", e, exc_info=True)

    def open_hierarchy_import_dialog(self):
        file_path = open_file_dialog(
            title="Select Hierarchy", filetypes={"Hierarchy": "*.xml"}
        )

        if not file_path:
            return

        with open(file_path) as f:
            xml = f.read()

        def on_import(hierarchy):
            new_objects = [
                r.result
                for r in hierarchy.objects.values()
                if r.action == MergeAction.NEW
            ]
            self.logger.info(f"Imported hierarchy of {len(new_objects)} elements")

            if hierarchy.pin_objects:
                for obj in new_objects:
                    self.add_pinned_object(obj)

            self.regenerate()
            self.jump_to_object(hierarchy.root_id)

        import_hierarchy(self.beh, xml, on_import)

    def open_mirror_skeleton_dialog(self):
        tag = f"{self.tag}_bone_mirror_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        skeleton_mirror_dialog(self.loaded_skeleton_path, tag=tag)

    def verify_behavior(self):
        if self._busy:
            return

        self._busy = True
        loading = common_loading_indicator("Validating behavior...")

        try:
            verify_behavior(self.beh)
            # TODO summary dialog?
            logging.info("Validation complete, check log for results!")
        finally:
            dpg.delete_item(loading)
            self._busy = False

    def open_apply_template_dialog(self, template_file: str):
        tag = f"{self.tag}_apply_template_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        def on_template_finished(
            sender: str, new_objects: list[HkbRecord], user_data: Any
        ):
            # This is a bit ugly, but so is adding more stuff to ids
            pin_objects = dpg.get_value(f"{sender}_pin_objects")
            if pin_objects:
                for obj in new_objects:
                    self.add_pinned_object(obj.object_id)

            self.regenerate()

        apply_template_dialog(
            self.beh,
            template_file,
            on_template_finished,
            tag=tag,
        )

    def open_guide(self) -> None:
        import webbrowser

        self.logger.info(
            "Opening website. An offline version of the guide can be found inside the docs/ folder!"
        )
        webbrowser.open("https://ndahn.github.io/HkbEditor/howto/howto/")

    def close_all_dialogs(self) -> None:
        dialogs = [
            "_edit_variables_dialog",
            "_edit_events_dialog",
            "_edit_animation_names_dialog",
            "_search_dialog",
            "_state_graph_dialog",
            "_create_object_dialog",
            "_register_clip_dialog",
            "_create_cmsg_dialog",
            "_bone_mirror_dialog",
            "_apply_template_dialog",
        ]

        for dlg in dialogs:
            dpg.delete_item(f"{self.tag}{dlg}")

    def open_about_dialog(self) -> None:
        tag = f"{self.tag}_about_dialog"
        if dpg.does_item_exist(tag):
            dpg.show_item(tag)
            dpg.focus_item(tag)
            return

        about_dialog(tag=tag)
        
        dpg.split_frame()
        center_window(tag)
