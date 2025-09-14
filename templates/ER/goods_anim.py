from typing import Literal
from hkb_editor.templates import *
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfo_Flags as TransitionFlags,
)


def run(
    ctx: TemplateContext,
    mode: Literal["oneshot", "enchant", "both"] = "oneshot",
    name: str = "MyItem",
    normal_use_anim: Animation = None,
    backhandsword_anim: Animation = None,
    duelingshield_anim: Animation = None,
):
    """New Usable Item

    Creates a new usable item that can be used as a oneshot, for weapon enchants, or both. The item will be used like every other regular item. For weapon buff items, the 'W_ItemWeaponEnchant' (or 'W_ItemWeaponEnchant_Upper') event is responsible.

    Oneshot items will only use the 'normal_use_anim'. Weapon buff items should also specify the 'backhandblade_anim' and 'duelingshield_ainm'. If not specified, the 'normal_use_anim' will be used instead.

    Author: FloppyDonuts
    
    Status: untested

    Parameters
    ----------
    ctx : TemplateContext
        The template context.
    mode : Literal[&quot;oneshot&quot;, &quot;enchant&quot;, &quot;both&quot;], optional
        The kind of item to generate.
    name : str, optional
        The name of your item, preferably in CamelCase.
    normal_use_anim : Animation, optional
        Animation used for oneshot items and regular weapons.
    backhandsword_anim : Animation, optional
        Animation used when enchanting backhand swords.
    duelingshield_anim : Animation, optional
        Animation used when enchanting dueling shields.
    """
    ####
    # Self-transition
    ####
    selftrans_clip = ctx.new_clip(normal_use_anim)

    selftrans_blend, selftrans_cmsg = ctx.create_blend_chain(
        selftrans_clip,
        normal_use_anim,
        name + "_CMSG02",
        enableScript=False,
        enableTae=False,
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    # Item_SM
    # TODO searches can be accelerated by searching from the appropriate statemachine
    selftrans_gen = ctx.find("name:ItemOneshot_SelfTrans type_name:hkbBlenderGenerator")
    ctx.array_add(selftrans_gen, "children", selftrans_blend)

    selftrans_upper_blend, selftrans_upper_cmsg = ctx.create_blend_chain(
        selftrans_clip,
        normal_use_anim,
        name + "_CMSG01",
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        animeEndEventType=AnimeEndEventType.NONE,
        checkAnimEndSlotNo=1,
    )
    # Item_Upper_SM
    selftrans_upper_gen = ctx.find(
        "name:ItemOneshot_SelfTrans type_name:hkbBlenderGenerator"
    )
    ctx.array_add(selftrans_upper_gen, "children", selftrans_upper_blend)

    ####
    # Oneshot
    ####
    if mode in ("oneshot", "both"):
        oneshot_clip = ctx.new_clip(normal_use_anim)
        oneshot_blend, oneshot_cmsg = ctx.create_blend_chain(
            oneshot_clip,
            normal_use_anim,
            name + "_CMSG",
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            enableScript=False,
            enableTae=False,
        )
        # Item_SM
        oneshot_gen = ctx.find("name:ItemOneshot type_name:hkbBlenderGenerator")
        ctx.array_add(oneshot_gen, "children", oneshot_blend)

        oneshot_upper_blend, oneshot_upper_cmsg = ctx.create_blend_chain(
            oneshot_clip,
            normal_use_anim,
            name + "_CMSG",
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )
        # Item_Upper_SM
        oneshot_upper_gen = ctx.find(
            "name:ItemOneshot_Upper type_name:hkbBlenderGenerator"
        )
        ctx.array_add(oneshot_upper_gen, "children", oneshot_upper_blend)

    ####
    # Weapon buff items
    ####
    if mode in ("enchant", "both"):
        if backhandsword_anim is None:
            backhandsword_anim = normal_use_anim

        if duelingshield_anim is None:
            duelingshield_anim = normal_use_anim

        enchant_event = ctx.event("W_ItemWeaponEnchant")
        weapon_type_var = ctx.variable("ItemWeaponType")
        transition_flags = TransitionFlags(3584)

        hand_change_state = ctx.find("name:HandChangeStart")
        hand_change_transition_ptr = hand_change_state["transitions"]
        normalitem_transition = ctx.new_transition_info(
            0,
            enchant_event,
            transition=hand_change_transition_ptr.get_value(),
            flags=transition_flags,
        )

        normalitem_sm = ctx.find("name:NormalItem_SM")
        ctx.array_add(
            normalitem_sm, "wildcardTransitions/transitions", normalitem_transition
        )

        normalitem_clip00 = ctx.new_clip(normal_use_anim)
        normalitem_backhandsword_clip00 = ctx.new_clip(backhandsword_anim)
        normalitem_duelingshield_clip00 = ctx.new_clip(duelingshield_anim)

        normalitem_cmsg00 = ctx.new_cmsg(
            normal_use_anim.anim_id,
            name="ItemWeaponEnchant_CMSG00",
            generators=[normalitem_clip00],
            enableScript=False,
            enableTae=False,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )
        normalitem_backhandsword_cmsg00 = ctx.new_cmsg(
            backhandsword_anim.anim_id,
            name="ItemWeaponEnchant_BackhandSword_CMSG00",
            generators=[normalitem_backhandsword_clip00],
            enableScript=False,
            enableTae=False,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )
        normalitem_duelingshield_cmsg00 = ctx.new_cmsg(
            duelingshield_anim.anim_id,
            name="ItemWeaponEnchant_DuelingShield_CMSG00",
            generators=[normalitem_duelingshield_clip00],
            enableScript=False,
            enableTae=False,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )

        normalitem_selector = ctx.new_selector(
            weapon_type_var,
            name="ItemWeaponEnchant Selector",
            generators=[
                normalitem_cmsg00,
                normalitem_backhandsword_cmsg00,
                normalitem_duelingshield_cmsg00,
            ],
            selectedIndexCanChangeAfterActivate=True,
        )

        normalitem_state = ctx.new_statemachine_state(
            name="ItemWeaponEnchant",
            generator=normalitem_selector,
        )

        ctx.array_add(normalitem_sm, "states", normalitem_state)

        # Upper half-blend
        enchant_upper_event = ctx.event("W_ItemWeaponEnchant_Upper")
        default_transition = ctx.find("name:DefaultTransition")

        normalitem_upper_transition = ctx.new_transition_info(
            0,
            enchant_upper_event,
            transition=default_transition,
            flags=transition_flags,
        )

        normalitem_upper_sm = ctx.find("name:NormalItem_Upper_SM")
        ctx.array_add(
            normalitem_upper_sm,
            "wildcardTransitions/transitions",
            normalitem_upper_transition,
        )

        normalitem_upper_cmsg00 = ctx.new_cmsg(
            normal_use_anim.anim_id,
            name="ItemWeaponEnchant_CMSG",
            generators=[normalitem_clip00],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )
        normalitem_upper_backhandsword_cmsg00 = ctx.new_cmsg(
            backhandsword_anim.anim_id,
            name="ItemWeaponEnchant_BackhandSword_CMSG",
            generators=[normalitem_backhandsword_clip00],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )
        normalitem_upper_duelingshield_cmsg00 = ctx.new_cmsg(
            duelingshield_anim.anim_id,
            name="ItemWeaponEnchant_DuelingShield_CMSG",
            generators=[normalitem_duelingshield_clip00],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )

        normalitem_upper_selector = ctx.new_selector(
            weapon_type_var,
            name="ItemWeaponEnchant_Upper Selector",
            generators=[
                normalitem_upper_cmsg00,
                normalitem_upper_backhandsword_cmsg00,
                normalitem_upper_duelingshield_cmsg00,
            ],
            selectedIndexCanChangeAfterActivate=True,
        )

        normalitem_upper_state = ctx.new_record(
            "hkbStateMachine::StateInfo",
            name="ItemWeaponEnchant_Upper",
            generator=normalitem_upper_selector,
            probability=1,
            enable=True,
        )

        ctx.array_add(normalitem_upper_sm, "states", normalitem_upper_state)
