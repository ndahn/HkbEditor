from hkb_editor.templates import *


# See SwordArtsOneShotCategory in c0000.hks
weapon_variations = [
    200,    # Large
    300,    # Polearm
    2000,   # Short Sword/Dagger
    2400,   # Twinblade
    2800,   # Curved Sword
    4200,   # Fist/Martial Arts/Perfume/BeastClaw
    4700,   # Large Shield
    4800,   # Small Shield
    5800,   # Backhand Sword
    5900,   # Dueling Shield
]


def run(
    ctx: TemplateContext,
    category: int = 600,
    regular: bool = True,
    follow_ups: bool = True,
    stance: bool = False,
    charge: bool = False,
    shield: bool = False,
    rolling: bool = False,
    add_cancels: bool = False,
    weapon_large: bool = True,
    weapon_polearm: bool = False,
    weapon_shortsword_dagger: bool = False,
    weapon_twinblade: bool = False,
    weapon_curvedsword: bool = False,
    weapon_hand: bool = False,
    weapon_largeshield: bool = False,
    weapon_smallshield: bool = False,
    weapon_backhandsword: bool = False,
    weapon_duelingshield: bool = False,
):
    """Ash of War

    Registers animation clips used in ashes of war. Entries that already exist will be skipped.
    
    Variations for specific weapon types are handled in HKS. Search for SwordArtsOneShotCategory in your c0000.hks for more details.

    Full instructions:
    https://ndahn.github.io/hkbeditor/templates/ash_of_war/

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    category : int
        The moveset category (the X part in aXXX_YYYYYY).
    regular : bool, optional
        Register a regular oneshot AOW (e.g. Lion's Claw).
    follow_ups : bool, optional
        Register follow up attacks for a oneshot AOW (e.g. Sword Dance).
    stance : bool, optional
        Register a stance AOW (e.g. Unsheathe).
    charge : bool, optional
        Register a charging AOW (e.g. Prelate's Charge).
    shield : bool, optional
        Register shield-specific animations (e.g. Shield Bash).
    rolling : bool, optional
        Register an AOW with directional input (e.g. Blindspot).
    add_cancels : bool, optional
        Add early and late cancels to the AOW (e.g. Carian Grandeur).
    weapon_large : bool, optional
        Add variations specific to large weapons (+200).
    weapon_polearm : bool, optional
        Add variations specific to polearm weapons (+300).
    weapon_shortsword_dagger : bool, optional
        Add variations specific to short sword/dagger weapons (+2000).
    weapon_twinblade : bool, optional
        Add variations specific to twinblade weapons (+2400).
    weapon_curvedsword : bool, optional
        Add variations specific to curved sword weapons (+2800).
    weapon_hand : bool, optional
        Add variations specific to fist/martial arts/perfume/beast claw weapons (+4200).
    weapon_largeshield : bool, optional
        Add variations specific to large shield weapons (+4700).
    weapon_smallshield : bool, optional
        Add variations specific to small shield weapons (+4800).
    weapon_backhandsword : bool, optional
        Add variations specific to backhand sword weapons (+5800).
    weapon_duelingshield : bool, optional
        Add variations specific to dueling shield weapons (+5900).
    """
    if not 0 <= category <= 999:
        raise ValueError("Category must be in [0..999]")

    attack_sm = ctx.find("name=SwordArts_SM")

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

    def add_cancel_anims(anim_ids: list[int]):
        for anim_id in anim_ids:
            if anim_id % 1000 in (0, 5, 30, 35, 40, 45) and anim_id + 1 not in anim_ids:
                anim_ids.append(anim_id + 1)  # early cancel
            if anim_id % 100 in (0, 5):
                anim_ids.append(anim_id + 2)  # late cancel

    def add_weapon_variations(anim_ids: list[int]):
        base_anims = list(anim_ids)

        for idx, enabled in enumerate([
            weapon_large,
            weapon_polearm,
            weapon_shortsword_dagger,
            weapon_twinblade,
            weapon_curvedsword,
            weapon_hand,
            weapon_largeshield,
            weapon_smallshield,
            weapon_backhandsword,
            weapon_duelingshield,
        ]):
            if enabled:
                offset = weapon_variations[idx]
                for anim_id in base_anims:
                    if anim_id % 1000 in (0, 5):
                        anim_ids.append(anim_id + offset)

    cat = f"a{category:03d}"

    if regular:
        anims = [40000, 40005]

        if follow_ups:
            anims.extend([40010, 40015, 40020, 40025])

        if add_cancels:
            add_cancel_anims(anims)

        add_weapon_variations(anims)

        for anim_id in anims:
            register_anim(anim_id)

    if stance:
        anims = [40050, 40051, 40052, 40053, 40056, 40057, 40060, 40065, 40070, 40075]

        if add_cancels:
            add_cancel_anims(anims)

        add_weapon_variations(anims)

        for anim_id in anims:
            # These will be in the DrawStance* SMs
            register_anim(anim_id, None)

    if charge:
        anims = [40000, 40003, 40004, 40005, 40008, 40009]

        for anim_id in anims:
            register_anim(anim_id)

    if shield:
        anims = [40040, 40045]

        if add_cancels:
            add_cancel_anims(anims)

        add_weapon_variations(anims)

        for anim_id in anims:
            register_anim(anim_id)

    if rolling:
        anims = [40080, 40081, 40082, 40083, 40084, 40085, 40086, 40087, 40088]
        for anim_id in anims:
            register_anim(anim_id)
