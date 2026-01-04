from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


def run(
    ctx: TemplateContext,
):
    """Dodge Stutter Fix

    Fixes the dodge stutter issue you get when registering dodge animations using ERClipGenerator.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/er/dodge_stutter_fix/
    
    Author: Managarm
    
    Status: confirmed

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    """
    evasion_sm = ctx.find("name=Evasion_SM")

    normal_state = ctx.find("name=Rolling", start_from=evasion_sm)
    selftrans_state = ctx.find("name=Rolling_Selftrans", start_from=evasion_sm)

    all_normal_cmsgs = ctx.find_all("type_name=CustomManualSelectorGenerator", start_from=normal_state)
    all_selftrans_cmsgs = ctx.find_all("type_name=CustomManualSelectorGenerator", start_from=selftrans_state)

    for normal_cmsg in all_normal_cmsgs:
        for normal_ptr in normal_cmsg["generators"]:
            # If the selftrans uses the same clip instance create a copy, otherwise
            # the clip will already be active and not do anything
            normal_clip = normal_ptr.get_target()
            copy = None

            # For ER we could just go by the name, i.e. RollingMediumFront_CMSG becomes
            # RollingMediumFront_Selftrans_CMSG, but iteration is fast and other games
            # or DLCs might contain spelling mistakes, etc.
            for self_cmsg in all_selftrans_cmsgs:
                for self_ptr in self_cmsg ["generators"]:
                    # Check if the pointers are referring to the same object
                    if self_ptr == normal_ptr:
                        if copy is None:
                            # Only make a copy when necessary, otherwise we create 
                            # detached objects
                            copy = ctx.make_copy(normal_clip)
                        
                        # Pointers can be set from records
                        self_ptr.set_value(copy)
                        break
                
                # We could break here if self_ptr was updated, but who knows what we'll find
