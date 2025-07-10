from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
)


def run(
    ctx: TemplateContext,
):
    """Fix Dodge Stutter

    Fixes the dodge stutter issue you get when duplicating dodges using ERClipGenerator.
    
    Each roll variant has two CMSGs: regular and self-transition, which through their ClipGenerators use the same animation. However, when ERClipGenerator copies the CMSGs, both CMSGs ends up using the same ClipGenerator. The stuttering appears because the same ClipGenerator cannot run multiple times in parallel.
    
    See PossiblyShiba's tutorial for additional details:
    https://docs.google.com/document/d/1kWycrniv1i_TxDFkJIXzFWrgKLe8kFbZcpMd2PAVGPo/edit?tab=t.0

    Author: Managarm

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    """
    targets = [
        "RollingLightFront",
        "RollingLightBack",
        "RollingLightLeft",
        "RollingLightRight",
        "RollingMediumFront",
        "RollingMediumBack",
        "RollingMediumLeft",
        "RollingMediumRight",
        "RollingHeavyFront",
        "RollingHeavyBack",
        "RollingHeavyLeft",
        "RollingHeavyRight",
    ]

    for target in targets:
        normal_cmsg = ctx.find(f"name:{target}_CMSG* type_name:CustomManualSelectorGenerator")
        
        if len(normal_cmsg["generators"]) < 2:
            continue

        selftrans_cmsg = ctx.find(f"name:{target}_Self* type_name:CustomManualSelectorGenerator")

        for orig_ptr in normal_cmsg["generators"]:
            # Create a copy of the original clip so the selftrans CMSG can run it in parallel
            orig_clip = orig_ptr.get_target()
            anim = orig_clip["animationName"]
            clip = ctx.new_clip(anim)

            for self_ptr in selftrans_cmsg["generators"]:
                # Replace any references to the original clip with our copy
                if self_ptr.get_value() == orig_ptr.get_value():
                    self_ptr.set_value(clip.object_id)
                    break
            else:
                # Not used after all
                ctx.delete(clip)
