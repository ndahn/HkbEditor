from hkb_editor.templates import *


def run(
    ctx: TemplateContext,
):
    """Rolling Arts Stutter Fix

    Same as for the dodge stutter, this fixes an issue which arises when the regular CMSG and self transition CMSG are using the same hkbClipGenerator instance.

    Rolling arts have an additional self transition category that activates for some AOW like quickstep and bloodhound step after repeated use. Since there's a transition from self transition 1 to self transition 2 these clips must also be separate.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/rollingarts_stutter_fix/

    Author: Kmstr

    Status: verified

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    """
    
    def separate_clips(cmsg_group1: list[HkbRecord], cmsg_group2: list[HkbRecord]) -> None:
        for cmsg1 in cmsg_group1:
            for ptr1 in cmsg1["generators"]:
                # If the selftrans uses the same clip instance create a copy, otherwise
                # the clip will already be active and not do anything
                clip1 = ptr1.get_target()
                copy = None

                # For ER we could just go by the name, i.e. RollingMediumFront_CMSG becomes
                # RollingMediumFront_Selftrans_CMSG, but iteration is fast and other games
                # or DLCs might contain spelling mistakes, etc.
                for cmsg2 in cmsg_group2:
                    for ptr2 in cmsg2 ["generators"]:
                        # Check if the pointers are referring to the same object
                        if ptr2 == ptr1:
                            if copy is None:
                                # Only make a copy when necessary, otherwise we create 
                                # detached objects
                                copy = ctx.make_copy(clip1)
                            
                            # Pointers can be set from records
                            ptr2.set_value(copy)
                            break
                    
                    # We could break here if ptr2 was updated, but who knows what we'll find

    swordarts_sm = ctx.find("name=SwordArts_SM")

    normal_state = ctx.find("name=SwordArtsRolling", start_from=swordarts_sm)
    selftrans1_state = ctx.find("name=SwordArtsRolling_SelfTrans", start_from=swordarts_sm)
    selftrans2_state = ctx.find("name=SwordArtsRolling_SelfTrans2", start_from=swordarts_sm)

    all_normal_cmsgs = ctx.find_all("type_name=CustomManualSelectorGenerator", start_from=normal_state)
    all_selftrans_cmsgs_1 = ctx.find_all("type_name=CustomManualSelectorGenerator", start_from=selftrans1_state)
    all_selftrans_cmsgs_2 = ctx.find_all("type_name=CustomManualSelectorGenerator", start_from=selftrans2_state)

    separate_clips(all_normal_cmsgs, all_selftrans_cmsgs_1 + all_selftrans_cmsgs_2)
    separate_clips(all_selftrans_cmsgs_1, all_selftrans_cmsgs_2)
