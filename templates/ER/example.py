from typing import Literal
from hkb_editor.templates import *


# Every template MUST have a function called "run"
def run(
    # Always first
    ctx: TemplateContext,
    # Will become an integer input in the dialog
    some_value: int,
    # Will allow the user to pick an animation using a search dialog
    animation: Animation,
    # Will become a combobox where the user can pick either "a" or "b"
    choice: Literal["a", "b"] = "a",
):
    """Example template

    The short description (i.e. the first line of this docstring) will appear in
    the menu, so keep it very short (< 25 characters). All subsequent paragraphs 
    will become text that is shown in the dialog.

    The context variable will always be the first parameter passed. All subsequent
    parameters will be exposed in the dialog for the user to fill in. Their type
    will be deduced preferably from the type hint, then the docstring below, then
    the default value (if any). If the type cannot be deduced the template will be
    rejected. The docstrings below are optional but recommended as they will become
    tooltips.

    For now only the following types will be supported:
    - simple types (int, float, bool, str)
    - choices (Literal of simple types)
    - known constants (Animation, Event, Variable)
    - other behavior objects (HkbRecord, no defaults)

    Defaults for Animations, Events and Variables may be provided as int or string.
    Defaults for HkbRecord objects may be provided as a string representing an 
    object ID or lucene search string to preselect a matching object.

    Please try to follow these guidelines, especially when submitting new scripts
    to be included in future releases.

    P.S.: templates will not be loaded until they are executed, only parsed.

    Author: Managarm

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    throw_id : int
        The ID of the new throw attack.
    cmsg_name : str
        Name of the CMSG.
    animation : Animation
        The animation to use.
    """
    # Create objects. They'll be added to the behavior automatically if either
    # generate_id is True or an object_id is provided. Any attributes you don't
    # specify will default to their type default (i.e. 0 for int, 0.0 for float,
    # "" for str, False for bool, object0 for pointers, etc.). This includes
    # flags and enums.
    cmsg = ctx.new_record(
        "CustomManualSelectorGenerator",
        name="My_CMSG",
        enableScript=True,
        enableTae=True,
    )

    # Uses our lucene search syntax. See hkb_editor.hkb.query for details
    parent = ctx.find("name:'Root_SM'")

    # The object has already been added to the xml in create(), but it still 
    # needs to be linked to the hierarchy
    ctx.set(parent, generator=cmsg)

    # You should only use the functions provided in hkb_editor.templates.*. Any
    # other interactions may result in unspecified behavior. If you feel like
    # something is missing please contact me.
