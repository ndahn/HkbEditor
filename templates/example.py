from typing import Literal
from hkb_editor.templates import *


# Every template MUST have a function called "run"
def run(
    # Always first
    ctx: TemplateContext,
    # Will allow the user to pick an animation using a search dialog
    animation: Animation,
    # Will become an integer input in the dialog
    cmsg_name: str,
    # Will become a combobox where the user can pick either "a" or "b"
    choice: Literal["a", "b"] = "a",
):
    """Example template

    This template should serve as an example of how to write new templates. When opening it in the editor, you can explore its code for yourselve by clicking the "Source" button below this text.

    # About docstrings
    The short description (that is, the first line of this docstring) will appear in
    the menu, so keep it very short (< 25 characters). All subsequent paragraphs 
    will become text that is shown in the dialog.

    There is very limited support for markdown-like formatting in the form of: 
    ```
    - # Headings (only level 0, ends at the next heading or double empty line)
    - -/* bullet points
    - ``` code blocks (which the user can copy from)
    - links (must start with http on a new line)
    ```

    # Template arguments
    The context variable will always be the first parameter passed. All subsequent
    parameters will be exposed in the dialog for the user to fill in. Their type
    will be deduced preferably from the type hint, then the docstring, then the 
    default value (if any). If the type cannot be deduced the template will be
    rejected. The following argument types will be supported:

    - simple types (int, float, bool, str)
    - choices (Literal of simple types)
    - known constants (Animation, Event, Variable)
    - other behavior objects (HkbRecord, defaults ignored)
    - any other type will cause the template to be rejected.

    Defaults for Animations, Events and Variables may be provided as int or string.
    Defaults for HkbRecord objects may be provided as a string representing an 
    object ID or lucene search string to preselect a matching object.


    Please try to follow these guidelines, especially when submitting new scripts
    to be included in future releases.

    P.S.: template code will not be truly loaded until it is executed.

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
    # The template is responsible for verifying passed arguments. However, future 
    # versions will consider all arguments without defaults as required, so the 
    # template won't be executed unless the user has specified them.
    if not cmsg_name or not animation:
        raise ValueError("Missing parameters")
    
    # Create a new CMSG with defaults and add it to the behavior. It will not be 
    # attached anywhere yet. When creating objects with names, try to follow the 
    # typical naming conventions (e.g. adding _CMSG to then name of a CMSG).
    cmsg = ctx.new_cmsg(
        animation.anim_id,
        name=cmsg_name,
        enableScript=False,
    )

    # Create a new ClipGenerator. We still have to link it to another object, 
    # usually a CMSG.
    clip = ctx.new_clip(animation)

    # We could have created the ClipGenerator first and pass it immediately when 
    # creating the CMSG, but this is a tutorial after all
    ctx.set(cmsg, generators=[clip])

    # Uses the search syntax to find the first node matching it. Will throw an
    # exception if no node matches. Be aware that names are not required to be 
    # unique. Add additional filters like 'type_name:CustomManualSelectorGenerator' 
    # to make sure you find what you want.
    found_object = ctx.find(f"name:'{cmsg_name}'")
    print(f"Found new CMSG with name {found_object['name']}")

    # Where possible you should only use the functions in hkb_editor.templates.*. 
    # This ensures that any modifications will be undoable in case the template 
    # fails or the user wants to undo the outcome. 

    # The template API already has many functions covering the most common and tedious
    # tasks. Check out the other examples as well as templates/context.py and 
    # templates/common.py. However, if you feel like some important functionality is 
    # missing please contact me.
