from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    hkbClipGenerator_PlaybackMode as PlaybackMode
)

def run(
    ctx: TemplateContext,
    category: int = 600,
    reference_category: int = 25,
    right: bool = True,
    both: bool = True,
    dual: bool = False,
    left: bool = False,
    backstab: bool = False,
    special: bool = False,
    warrior: bool = False,
    jump: bool = False,
    jump_swing_variations: bool = False,
    ride: bool = False,
):
    """Weapon Moveset

    Creates ClipGenerators that are typically used in weapon movesets, e.g. for right-handed attacks it will register 030000, 030010, etc. Entries that already exist will be skipped.

    Note that special and warrior attacks will only be registered if right and/or both are checked. Jump attacks will only be registered if right, both, and/or dual are checked.

    Full instructions:
    https://ndahn.github.io/HkbEditor/templates/er/weapon_moveset/

    Author: Managarm

    Status: confirmed

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    category : int
        The moveset category (the X part in aXXX_YYYYYY).
    reference_category : int
        The moveset category to be used as a reference (the X part in aXXX_YYYYYY).
    right : bool, optional
        Register right-handed attacks.
    both : bool, optional
        Register both-handed attacks.
    dual : bool, optional
        Register dual wield attacks.
    left : bool, optional
        Register left-handed attacks.
    backstab : bool, optional
        Register backstab animations.
    special : bool, optional
        Register special attacks (e.g. Braggart's Roar).
    warrior : bool, optional
        Register warrior attacks (e.g. Barbaric Roar).
    jump : bool, optional
        Register jump and landing attacks.
    jump_swing_variations : bool, optional
        Register jump and landing attack swing variations (aXXX_YYYY71, aXXX_YYYY72 and aXXX_YYYY81, aXXX_YYYY82).
    ride : bool, optional
        Register ride attacks.
    """
    if not 0 <= category <= 999:
        raise ValueError("Category must be in [0..999]")

    def register_anim(statemachine, anim_id: int, playback_mode: PlaybackMode = PlaybackMode.SINGLE_PLAY):
        anim = ctx.animation(f"{cat}_{anim_id:06d}")

        # Why is it throwing an exception? Ugh
        reference_anim = None;
        reference_anim_name = f"a{reference_category:03d}_{anim_id:06d}"
        try:
            reference_anim = ctx.animation(reference_anim_name, False)

        except ValueError as e:
            print(f"The reference moveset doesn't have an animation '{reference_anim_name}'")

        # Find the CMSG the animation should be registered in
        cmsg_list = ctx.find_all(
            f"type_name=CustomManualSelectorGenerator animId={anim_id}",
            start_from=statemachine,
        )
        if not cmsg_list:
            raise ValueError(f"Could not find CMSGs for animId={anim_id}")

        # Add the clips to all matching CMSGs
        for cmsg in cmsg_list:
            clip_generators = cmsg["generators"];

            # Check for already registered clips
            for ptr in clip_generators:
                name = ptr.get_target()["animationName"]

                if name.get_value() == anim.name:
                    # Clip already exists
                    # Try to add variable binding set to it?
                    return

            # If the reference clip has a variable binding set, we should create one too
            reference_clip = None
            for ptr in clip_generators:
                ref = ptr.get_target()
                name = ref["animationName"]

                if reference_anim and name.get_value() == reference_anim.name:
                    reference_clip = ref
                    break

            if True:
                clip = ctx.new_clip(anim, mode = playback_mode)

                # Bind the variable if required
                if reference_clip:
                    reference_bindset_ptr = reference_clip["variableBindingSet"];

                    if reference_bindset_ptr.get_value():
                        print(f"CMSG '{cmsg}' uses clips with variableBindingSet, copying one from the reference clip '{reference_clip["animationName"]}'")

                        clip_bindset = ctx.make_copy(reference_bindset_ptr.get_target())
                        clip["variableBindingSet"].set_value(clip_bindset)

                clip_generators.append(clip)

    cat = f"a{category:03d}"
    attack_sm: HkbRecord = ctx.find("name=Attack_SM")

    if right:
        for anim_id in [
            30000,
            30010,
            30020,
            30030,
            30040,
            30050,
            30200,
            30210,
            30300,
            30400,
            30500,
            30501,
            30505,
            30510,
            30515,
            30700,
        ]:
            register_anim(attack_sm, anim_id)

    if both:
        for anim_id in [
            32000,
            32010,
            32020,
            32030,
            32040,
            32050,
            32200,
            32210,
            32300,
            32400,
            32500,
            32501,
            32505,
            32510,
            32515,
            32700,
        ]:
            register_anim(attack_sm, anim_id)

    if dual:
        for anim_id in [34000, 34010, 34020, 34030, 34200, 34300, 34400]:
            register_anim(attack_sm, anim_id)

    if left:
        for anim_id in [35000, 35010, 35020, 35030, 35040, 35050]:
            register_anim(attack_sm, anim_id)

    if backstab:
        for anim_id in [31700, 31710, 31719, 31720, 31730, 31750, 31760]:
            # Most are in Throw_SM, but 31719 is under "ThrowBackStab NetSync Script"
            register_anim(None, anim_id)

    if special:
        if right:
            for anim_id in [30600, 30601, 30605, 30610, 30615]:
                register_anim(attack_sm, anim_id)
        if both:
            for anim_id in [32600, 32601, 32605, 32610, 32615]:
                register_anim(attack_sm, anim_id)

    if warrior:
        if right:
            for anim_id in [30620, 30621, 30625, 30630, 30635]:
                register_anim(attack_sm, anim_id)
        if both:
            for anim_id in [32620, 32621, 32625, 32630, 32635]:
                register_anim(attack_sm, anim_id)

    if jump:
        jump_sm = ctx.find("name='NewJump StateMachine'")

        if right:
            for anim_id in [
                31030,
                31040,
                31050,
                31070,
                31230,
                31240,
                31250,
                31270,
            ]:
                register_anim(jump_sm, anim_id)

            for anim_id in [31060, 31260]:
                register_anim(jump_sm, anim_id, PlaybackMode.LOOPING)

            if jump_swing_variations:
                for anim_id in [
                    31071,
                    31072,
                    31081,
                    31082,
                    31271,
                    31272,
                    31281,
                    31282,
                ]:
                    register_anim(jump_sm, anim_id)

        if both:
            for anim_id in [
                33030,
                33040,
                33050,
                33070,
                33230,
                33240,
                33250,
                33270,
            ]:
                register_anim(jump_sm, anim_id)

            for anim_id in [33060, 33260]:
                register_anim(jump_sm, anim_id, PlaybackMode.LOOPING)

            if jump_swing_variations:
                for anim_id in [
                    33071,
                    33072,
                    33081,
                    33082,
                    33271,
                    33272,
                    33281,
                    33282,
                ]:
                    register_anim(jump_sm, anim_id)

        if dual:
            for anim_id in [34530, 34540, 34550, 34570]:
                register_anim(jump_sm, anim_id)

            register_anim(jump_sm, 34560, PlaybackMode.LOOPING)

            if jump_swing_variations:
                for anim_id in [
                    34571,
                    34572,
                    34581,
                    34582
                ]:
                    register_anim(jump_sm, anim_id)

    if ride:
        ride_sm = ctx.find("name=Ride_NoThrow_SM")

        for anim_id in [
            38000,
            38010,
            38020,
            38100,
            38110,
            38200,
            38300,
            39000,
            39010,
            39020,
            39100,
            39110,
            39200,
            39300,
        ]:
            register_anim(ride_sm, anim_id)
