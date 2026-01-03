from hkb_editor.templates import *


def run(
    ctx: TemplateContext,
    category: int = 600,
    right: bool = True,
    both: bool = True,
    dual: bool = False,
    left: bool = False,
    backstab: bool = False,
    special: bool = False,
    warrior: bool = False,
    jump: bool = False,
    ride: bool = False,
):
    """Weapon Moveset

    Creates ClipGenerators that are typically used in weapon movesets, e.g. for right-handed attacks it will register 030000, 030010, etc. Entries that already exist will be skipped.

    Note that special and warrior attacks will only be registered if right and/or both are checked.

    Note that jump attacks will only be registered if right, both, and/or dual are checked.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/er/weapon_moveset/

    Author: Managarm

    Status: confirmed

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    category : int
        The moveset category (the X part in aXXX_YYYYYY).
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
    ride : bool, optional
        Register ride attacks.
    """
    if not 0 <= category <= 999:
        raise ValueError("Category must be in [0..999]")

    attack_sm: HkbRecord = ctx.find("name=Attack_SM")

    def register_anim(anim_id: int, statemachine=attack_sm):
        anim = ctx.animation(f"{cat}_{anim_id:06d}")

        # Find the CMSG the animation should be registered in
        cmsg = ctx.find(
            f"type_name=CustomManualSelectorGenerator animId={anim_id}",
            start_from=statemachine,
        )
        if not cmsg:
            raise ValueError(f"Could not find CMSG for animId={anim_id}")

        for ptr in cmsg["generators"]:
            if ptr.get_target()["animationName"] == anim.name:
                # Clip already exists
                return

        if True:
            clip = ctx.new_clip(anim)
            cmsg["generators"].append(clip)

    cat = f"a{category:03d}"

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
            register_anim(anim_id)

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
            register_anim(anim_id)

    if dual:
        for anim_id in [34000, 34010, 34020, 34030, 34200, 34300, 34400]:
            register_anim(anim_id)

    if left:
        for anim_id in [35000, 35010, 35020, 35030, 35040, 35050]:
            register_anim(anim_id)

    if backstab:
        for anim_id in [31700, 31710, 31719, 31720, 31730, 31750, 31760]:
            # Most are in Throw_SM, but 31719 is under "ThrowBackStab NetSync Script"
            register_anim(anim_id, None)

    if special:
        if right:
            for anim_id in [30600, 30601, 30605, 30610, 30615]:
                register_anim(anim_id)
        if both:
            for anim_id in [32600, 32601, 32605, 32610, 32615]:
                register_anim(anim_id)

    if warrior:
        if right:
            for anim_id in [30620, 30621, 30625, 30630, 30635]:
                register_anim(anim_id)
        if both:
            for anim_id in [32620, 32621, 32625, 32630, 32635]:
                register_anim(anim_id)

    if jump:
        jump_sm = ctx.find("name='NewJump StateMachine'")

        if right:
            for anim_id in [
                31030,
                31040,
                31050,
                31060,
                31070,
                31230,
                31240,
                31250,
                31260,
                31270,
            ]:
                register_anim(anim_id, jump_sm)
        if both:
            for anim_id in [
                33030,
                33040,
                33050,
                33060,
                33070,
                33230,
                33240,
                33250,
                33260,
                33270,
            ]:
                register_anim(anim_id, jump_sm)
        if dual:
            for anim_id in [34530, 34540, 34550, 34560, 34570]:
                register_anim(anim_id, jump_sm)

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
            register_anim(anim_id, ride_sm)
