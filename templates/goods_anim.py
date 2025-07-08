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
    animation: Animation = None,
    enchant_backhandblade: Animation = None,
    enchant_duelingshield: Animation = None,
):
    ####
    # Self-transition
    ####
    selftrans_clip = ctx.new_clip(animation)

    selftrans_blend, selftrans_cmsg = ctx.create_blend_chain(
        selftrans_clip,
        animation,
        name + "_CMSG02",
        enableScript=False,
        enableTae=False,
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        animeEndEventType=AnimeEndEventType.NONE,
    )
    # Item_SM
    selftrans_gen = ctx.find("name:ItemOneshot_SelfTrans type_name:hkbBlenderGenerator")
    ctx.array_add(selftrans_gen, "children", selftrans_blend.object_id)

    selftrans_upper_blend, selftrans_upper_cmsg = ctx.create_blend_chain(
        selftrans_clip,
        animation,
        name + "_CMSG01",
        offsetType=CmsgOffsetType.IDLE_CATEGORY,
        animeEndEventType=AnimeEndEventType.NONE,
        checkAnimEndSlotNo=1,
    )
    # Item_Upper_SM
    selftrans_upper_gen = ctx.find(
        "name:ItemOneshot_SelfTrans type_name:hkbBlenderGenerator"
    )
    ctx.array_add(selftrans_upper_gen, "children", selftrans_upper_blend.object_id)

    ####
    # Oneshot
    ####
    if mode in ("oneshot", "both"):
        oneshot_clip = ctx.new_clip(animation)
        oneshot_blend, oneshot_cmsg = ctx.create_blend_chain(
            oneshot_clip,
            animation,
            name + "_CMSG",
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            enableScript=False,
            enableTae=False,
        )
        # Item_SM
        oneshot_gen = ctx.find("name:ItemOneshot type_name:hkbBlenderGenerator")
        ctx.array_add(oneshot_gen, "children", oneshot_blend.object_id)

        oneshot_upper_blend, oneshot_upper_cmsg = ctx.create_blend_chain(
            oneshot_clip,
            animation,
            name + "_CMSG",
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )
        # Item_Upper_SM
        oneshot_upper_gen = ctx.find(
            "name:ItemOneshot_Upper type_name:hkbBlenderGenerator"
        )
        ctx.array_add(oneshot_upper_gen, "children", oneshot_upper_blend.object_id)

    ####
    # Weapon buff items
    ####
    if mode in ("enchant", "both"):
        enchant_event = ctx.get_event("W_ItemWeaponEnchant")
        weapon_type_var = ctx.get_variable("ItemWeaponType")
        transition_flags = TransitionFlags(3584)

        hand_change_state = ctx.find("name:HandChangeStart")
        hand_change_transition = hand_change_state["transitions"]
        normalitem_transition = ctx.new_transition_info(
            0,
            enchant_event,
            transition=hand_change_transition.object_id,
            flags=transition_flags,
        )

        normalitem_sm = ctx.find("name:NormalItem_SM")
        ctx.array_add(normalitem_sm, "wildcardTransitions", normalitem_transition.object_id)

        normalitem_clip00 = ctx.new_clip(animation)
        normalitem_backhandsword_clip00 = ctx.new_clip(enchant_backhandblade)
        normalitem_duelingshield_clip00 = ctx.new_clip(enchant_duelingshield)

        normalitem_cmsg00 = ctx.new_cmsg(
            name="ItemWeaponEnchant_CMSG00",
            animId=animation,
            generators=[normalitem_clip00],
            enableScript=False,
            enableTae=False,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )
        normalitem_backhandsword_cmsg00 = ctx.new_cmsg(
            name="ItemWeaponEnchant_BackhandSword_CMSG00",
            animId=enchant_backhandblade,
            generators=[normalitem_backhandsword_clip00],
            enableScript=False,
            enableTae=False,
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
        )
        normalitem_duelingshield_cmsg00 = ctx.new_cmsg(
            name="ItemWeaponEnchant_DuelingShield_CMSG00",
            animId=enchant_duelingshield,
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

        normalitem_state = ctx.new(
            "hkbStateMachine::StateInfo",
            name="ItemWeaponEnchant",
            generator=normalitem_selector.object_id,
            probability=1,
            enable=True,
        )

        ctx.array_add(normalitem_sm, "states", normalitem_state.object_id)

        # Upper half-blend
        enchant_upper_event = ctx.get_event("W_ItemWeaponEnchant_Upper")
        default_transition = ctx.find("name:DefaultTransition")

        normalitem_upper_transition = ctx.new_transition_info(
            0,
            enchant_upper_event,
            transition=default_transition.object_id,
            flags=transition_flags,
        )

        normalitem_upper_sm = ctx.find("name:NormalItem_Upper_SM")
        ctx.array_add.object_id(
            normalitem_upper_sm, "wildcardTransitions", normalitem_upper_transition
        )

        normalitem_upper_cmsg00 = ctx.new_cmsg(
            name="ItemWeaponEnchant_CMSG",
            animId=animation,
            generators=[normalitem_clip00],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )
        normalitem_upper_backhandsword_cmsg00 = ctx.new_cmsg(
            name="ItemWeaponEnchant_BackhandSword_CMSG",
            animId=enchant_backhandblade,
            generators=[normalitem_backhandsword_clip00],
            offsetType=CmsgOffsetType.IDLE_CATEGORY,
            animeEndEventType=AnimeEndEventType.NONE,
            checkAnimEndSlotNo=1,
        )
        normalitem_upper_duelingshield_cmsg00 = ctx.new_cmsg(
            name="ItemWeaponEnchant_DuelingShield_CMSG",
            animId=enchant_duelingshield,
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

        normalitem_upper_state = ctx.new(
            "hkbStateMachine::StateInfo",
            name="ItemWeaponEnchant_Upper",
            generator=normalitem_upper_selector.object_id,
            probability=1,
            enable=True,
        )

        ctx.array_add(normalitem_upper_sm, "states", normalitem_upper_state.object_id)
