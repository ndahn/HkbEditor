from typing import Any
import os
import logging
from dataclasses import dataclass

from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    hkbBlendCurveUtils_BlendCurve as BlendCurve,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfo_Flags as TransitionInfoFlags,
)


@dataclass
class Variable:
    index: int
    name: str


@dataclass
class Event:
    index: int
    name: str


@dataclass
class Animation:
    index: int
    name: str
    full_name: str

    @property
    def anim_id(self) -> int:
        return int(self.name.split("_")[-1])


@dataclass
class HkbRecordSpec:
    query: str = None
    type_name: str = None


class CommonActionsMixin:
    def __init__(self, behavior: HavokBehavior):
        """Provides convenience methods for common actions.

        Designed as a Mixin so that it can be passed around with a bound behavior (e.g. for template execution).

        Parameters
        ----------
        behavior : HavokBehavior
            The behavior the convenience functions will apply to.
        """
        self._behavior = behavior

    def __getattr__(self, name: str) -> Any:
        # Check if the class we're mixed with (if any) already has a logger
        if name == 'logger':
            logger = logging.getLogger(os.path.basename(self._behavior.file))
            object.__setattr__(self, 'logger', logger)
            return logger
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def get_record(self, reference: Any, default: Any = None) -> HkbRecord:
        """Safely retrieve the record referenced by the input.

        If the input is None or already a HkbRecord, simply retrieve it. If it's the ID of an existing object, resolve it. In all other cases treat it as a query string and return the first matching object.

        Parameters
        ----------
        reference : Any
            A reference to a record.
        default : Any, optional
            What to return if the reference can not be resolved.

        Returns
        -------
        HkbRecord
            The resolved record or None.
        """
        if reference is None:
            return None

        if isinstance(reference, HkbRecord):
            return reference

        if reference in self._behavior.objects:
            # Is it an object ID?
            return self._behavior.objects[reference]

        # Assume it's a query string
        return next(self._behavior.query(reference), default)

    def _resolve_variable(self, variable: Variable | str | int) -> int:
        if isinstance(variable, Variable):
            return variable.index
        elif isinstance(variable, str):
            return self._behavior.find_variable(variable)
        elif isinstance(variable, int):
            return variable

        raise ValueError(f"{variable} is not a valid variable")
    
    def _resolve_event(self, event: Event | str | int) -> int:
        if isinstance(event, Event):
            return event.index
        elif isinstance(event, str):
            return self._behavior.find_event(event)
        elif isinstance(event, int):
            return event

        raise ValueError(f"{event} is not a valid event")


    def _resolve_animation(self, animation: Animation | str | int) -> int:
        if isinstance(animation, Animation):
            return animation.index
        elif isinstance(animation, str):
            return self._behavior.find_animation(animation)
        elif isinstance(animation, int):
            return animation

        raise ValueError(f"{animation} is not a valid animation")

    def get_next_state_id(self, statemachine: HkbRecord) -> int:
        """Find the next state ID which is 1 higher than the highest one in use.

        Parameters
        ----------
        statemachine : HkbRecord
            The statemachine to search.

        Returns
        -------
        int
            The next free state ID.
        """
        max_id = 0
        state_ptr: HkbPointer

        for state_ptr in statemachine["states"]:
            state = state_ptr.get_target()
            state_id = state["stateId"].get_value()
            max_id = max(max_id, state_id)

        return max_id + 1

    def find_array_item(self, array: HkbArray, **conditions) -> HkbRecord:
        """Find an item in an array with specific attributes. If it's an array of pointers they will be resolved to their target objects automatically.

        Parameters
        ----------
        array : HkbArray
            The array to search
        conditions : dict[str, Any]
            Only return items whose fields have the specified values.

        Raises
        ------
        AttributeError
            If the array items do not have any of the specified fields.

        Returns
        -------
        HkbRecord
            The first item in the array matching the conditions, or None if no items match.
        """
        for item in array:
            if isinstance(item, HkbPointer):
                item = item.get_target()
        
            if item:
                if all(item[key].get_value() == val for key, val in conditions.items()):
                    return item
        
        return None

    def bind_variable(
        self,
        record: HkbRecord,
        path: str,
        variable: Variable | str | int,
    ) -> HkbRecord:
        """Bind a record field to a variable.

        This allows to control aspects of a behavior object through HKS or TAE. Most commonly used for ManualSelectorGenerators. Note that in HKS variables are referenced by their name, in all other places the variables' indices are used.

        If the record does not have a variableBindingSet yet it will be created. If the record already has a binding for the specified path it will be updated to the provided variable.

        Parameters
        ----------
        record : HkbRecord | str
            The record which should be bound.
        path : str
            Path to the record's member to bind, with deeper levels separated by /.
        variable : Variable | str | int
            The variable to bind the field to.

        Returns
        -------
        HkbRecord
            The variable binding set to which the field was bound.
        """
        binding_set_ptr: HkbPointer = record["variableBindingSet"]
        var_idx = self._resolve_variable(variable)

        with undo_manager.combine():
            if not binding_set_ptr.get_value():
                # Need to create a new variable binding set first
                binding_set_type_id = (
                    self._behavior.type_registry.find_first_type_by_name(
                        "hkbVariableBindingSet"
                    )
                )

                binding_set = HkbRecord.new(
                    self._behavior,
                    binding_set_type_id,
                    {
                        "indexOfBindingToEnable": -1,
                    },
                    object_id=self._behavior.new_id(),
                )

                self._behavior.add_object(binding_set)
                undo_manager.on_create_object(self._behavior, binding_set)

                binding_set_ptr.set_value(binding_set.object_id)
                undo_manager.on_update_value(
                    binding_set_ptr, None, binding_set.object_id
                )
            else:
                binding_set = binding_set_ptr.get_target()

            bindings: HkbArray = binding_set["bindings"]
            for bind in bindings:
                if bind["memberPath"] == path:
                    # Binding for this path already exists, update it
                    bound_var_idx = bind["variableIndex"]
                    old_value = bound_var_idx.get_value()
                    bound_var_idx.set_value(var_idx)
                    undo_manager.on_update_value(bound_var_idx, old_value, var_idx)
                    break
            else:
                # Create a new binding for the path
                bind = HkbRecord.new(
                    self._behavior,
                    bindings.element_type_id,
                    {
                        "memberPath": path,
                        "variableIndex": var_idx,
                        "bitIndex": -1,
                        "bindingType": 0,
                    },
                )
                bindings.append(bind)
                undo_manager.on_update_array_item(bindings, -1, None, bind)

        return binding_set

    def clear_variable_binding(
        self,
        record: HkbRecord,
        path: str,
    ) -> None:
        """Removes all variable bindings for the specified field path from this record. Will do nothing if the record in question does not (or can not) have a variable binding set.

        Parameters
        ----------
        record : HkbRecord
            The record to clear the variable binding set from. 
        path : str
            Path to the bound field.
        """
        # The record might not event support variableBindingSets, which is still fine
        binding_set_ptr: HkbPointer = record.get_field("variableBindingSet", None)
        if binding_set_ptr is None:
            return

        binding_set = binding_set_ptr.get_target()
        if binding_set is None:
            return

        bindings: HkbArray = binding_set["bindings"]
        bnd: HkbRecord

        for idx, bnd in enumerate(bindings):
            if bnd["memberPath"].get_value() == path:
                old_value = bindings.pop(idx)
                undo_manager.on_update_array_item(bindings, idx, old_value, None)

    def new_record(
        self,
        object_type_name: str,
        *,
        object_id: str = "<new>",
        **kwargs: Any,
    ) -> HkbRecord:
        """Create an arbitrary new hkb object. If an object ID is provided or generated, the object will also be added to the behavior.

        Note that when using this method you have to match the expected field type, so helper classes like Variable, Event and Animation cannot be used.

        Parameters
        ----------
        object_type_name : str
            The type of the object to generate. In decompiled hkb this is usually the comment under the `<object id="..." typeid="...">` line.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        kwargs:
            Any fields you want to set for the generated object. Fields not specified will use their type default (e.g. int will be 0, str will be empty, etc.). You may also specify paths (`subrecord/field`).

        Raises
        ------
        KeyError
            If kwargs contains any paths not found in the generated object.

        Returns
        -------
        HkbRecord
            The generated object.
        """
        type_id = self._behavior.type_registry.find_first_type_by_name(object_type_name)
        if object_id == "<new>":
            object_id = self._behavior.new_id()

        record = HkbRecord.new(
            self._behavior, type_id, path_values=kwargs, object_id=object_id
        )
        if record.object_id:
            self._behavior.add_object(record)
            undo_manager.on_create_object(self._behavior, record)

        self.logger.debug(f"Created new object {record}")

        return record

    def make_copy(
        self, source: HkbRecord | str, *, object_id: str = "<new>", **overrides
    ) -> HkbRecord:
        """Creates a copy of a record.

        Parameters
        ----------
        source : HkbRecord | str
            The record to copy.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        overrides : dict[str, Any]
            Values to change in the copy before returning it.

        Returns
        -------
        HkbRecord
            A copy of the source altered according to the specified overrides.
        """
        source = self.get_record(source)

        attributes = {k: v.get_value() for k, v in source.get_value().items()}
        attributes.update(**overrides)

        return self.new_record(source.type_name, object_id=object_id, **attributes)

    # Offer common defaults and highlight required settings for the most common objects
    # TODO document functions and their arguments

    def new_cmsg(
        self,
        *,
        object_id: str = "<new>",
        name: str = "",
        animId: Animation | str | int = 0,
        generators: list[HkbRecord | str] = None,
        enableScript: bool = True,
        enableTae: bool = True,
        offsetType: CmsgOffsetType = CmsgOffsetType.NONE,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        changeTypeOfSelectedIndexAfterActivate: ChangeIndexType = ChangeIndexType.NONE,
        checkAnimEndSlotNo: int = -1,
        **kwargs,
    ) -> HkbRecord:
        if isinstance(animId, Animation):
            animId = animId.name

        if isinstance(animId, str):
            # Assume it's an animation name
            animId = int(animId.split("_")[-1])

        if generators:
            generators = [self.get_record(obj).object_id for obj in generators]
        else:
            generators = []

        return self.new_record(
            "CustomManualSelectorGenerator",
            object_id=object_id,
            name=name,
            generators=generators,
            offsetType=offsetType.value,
            animId=animId,
            enableScript=enableScript,
            enableTae=enableTae,
            checkAnimEndSlotNo=checkAnimEndSlotNo,
            animeEndEventType=animeEndEventType,
            changeTypeOfSelectedIndexAfterActivate=changeTypeOfSelectedIndexAfterActivate,
            **kwargs,
        )

    def new_selector(
        self,
        variable: Variable | str | int,
        *,
        object_id: str = "<new>",
        name: str = "",
        generators: list[HkbRecord | str] = None,
        variableBindingSet: HkbRecord | str = None,
        generatorChangedTransitionEffect: HkbRecord | str = None,
        selectedIndexCanChangeAfterActivate: bool = False,
        **kwargs,
    ) -> HkbRecord:
        if generators:
            generators = [self.get_record(obj).object_id for obj in generators]
        else:
            generators = []

        variableBindingSet = self.get_record(variableBindingSet)
        generatorChangedTransitionEffect = self.get_record(generatorChangedTransitionEffect)

        kwargs.setdefault("sentOnClipEnd/id", -1)
        kwargs.setdefault("endOfClipEventId", -1)

        selector = self.new_record(
            "hkbManualSelectorGenerator",
            object_id=object_id,
            name=name,
            generators=generators,
            variableBindingSet=(
                variableBindingSet.object_id if variableBindingSet else None
            ),
            generatorChangedTransitionEffect=(
                generatorChangedTransitionEffect.object_id
                if generatorChangedTransitionEffect
                else None
            ),
            selectedIndexCanChangeAfterActivate=selectedIndexCanChangeAfterActivate,
            **kwargs,
        )

        if variable is not None:
            # Will create a new binding set if necessary
            self.bind_variable(selector, "selectedGeneratorIndex", variable)

        return selector

    def new_clip(
        self,
        animation: Animation | str | int,
        *,
        object_id: str = "<new>",
        name: str = None,
        playbackSpeed: int = 1,
        mode: PlaybackMode = PlaybackMode.SINGLE_PLAY,
        **kwargs,
    ) -> HkbRecord:
        anim_id = self._resolve_animation(animation)
        anim_name = self._behavior.get_animation(anim_id)

        if name is None:
            name = anim_name

        return self.new_record(
            "hkbClipGenerator",
            object_id=object_id,
            name=name,
            animationName=anim_name,
            playbackSpeed=playbackSpeed,
            animationInternalId=anim_id,
            mode=mode,
            **kwargs,
        )

    def new_statemachine_state(
        self,
        stateId: int,
        *,
        object_id: str = "<new>",
        name: str = "",
        transitions: HkbRecord | str = None,
        generator: HkbRecord | str = None,
        probability: float = 1.0,
        enable: bool = True,
        **kwargs,
    ) -> HkbRecord:
        transitions = self.get_record(transitions)
        generator = self.get_record(generator)

        return self.new_record(
            "hkbStateMachine::StateInfo",
            object_id=object_id,
            stateId=stateId,
            name=name,
            transitions=transitions.object_id if transitions else None,
            generator=generator.object_id if generator else None,
            probability=probability,
            enable=enable,
            **kwargs,
        )

    def new_transition_info_array(
        self,
        *,
        object_id: str = "<new>",
        transitions: list[HkbRecord] = None,
    ) -> HkbRecord:
        return self.new_record(
            "hkbStateMachine::TransitionInfoArray",
            object_id=object_id,
            transitions=transitions or [],
        )

    def new_transition_info(
        self,
        toStateId: int,
        eventId: Event | str | int,
        *,
        transition: HkbRecord | str = None,
        flags: TransitionInfoFlags = 0,
        **kwargs,
    ) -> HkbRecord:
        eventId = self._resolve_event(eventId)

        if transition is None:
            transition = next(
                self._behavior.query(
                    "DefaultTransition type_name:CustomTransitionEffect"
                ),
                None,
            )
        transition = self.get_record(transition)

        kwargs.setdefault("triggerInterval/enterEventId", -1)
        kwargs.setdefault("triggerInterval/exitEventId", -1)
        kwargs.setdefault("initiateInterval/enterEventId", -1)
        kwargs.setdefault("initiateInterval/exitEventId", -1)

        return self.new_record(
            "hkbStateMachine::TransitionInfo",
            toStateId=toStateId,
            eventId=eventId,
            transition=transition.object_id if transition else None,
            flags=flags,
            **kwargs,
        )

    def new_blender_generator_child(
        self,
        cmsg: HkbRecord | str,
        *,
        object_id: str = "<new>",
        weight: float = 1.0,
        worldFromModelWeight: int = 1,
        **kwargs,
    ) -> HkbRecord:
        cmsg = self.get_record(cmsg)

        return self.new_record(
            "hkbBlenderGeneratorChild",
            object_id=object_id,
            generator=cmsg.object_id if cmsg else None,
            weight=weight,
            worldFromModelWeight=worldFromModelWeight,
            **kwargs,
        )

    def new_layer_generator(
        self,
        *,
        object_id: str = "<new>",
        name: str = "",
        layers: list[HkbRecord | str] = None,
        indexOfSyncMasterChild: int = -1,
        flags: int = 0,  # TODO get proper flag type
        **kwargs,
    ) -> HkbRecord:
        if layers:
            layers = [self.get_record(l) for l in layers]
        else:
            layers = []

        return self.new_record(
            "hkbLayerGenerator",
            object_id=object_id,
            name=name,
            layers=layers,
            indexOfSyncMasterChild=indexOfSyncMasterChild,
            flags=flags,
            **kwargs,
        )

    def new_layer(
        self,
        *,
        object_id: str = "<new>",
        generator: HkbRecord | str = None,
        boneWeights: HkbRecord | str = None,
        useMotion: bool = False,
        weight: float = 0.5,
        fadeInDuration: float = 0.0,
        fadeOutDuration: float = 0.0,
        onEventId: Event | str | int = -1,
        offEventId: Event | str | int = -1,
        onByDefault: bool = False,
        fadeInOutCurve: BlendCurve = BlendCurve.SMOOTH,
        **kwargs,
    ) -> HkbRecord:
        generator = self.get_record(generator)
        boneWeights = self.get_record(boneWeights)
        onEventId = self._resolve_event(onEventId)
        offEventId = self._resolve_event(offEventId)

        blend_params = {
            "blendingControlData/weight": weight,
            "blendingControlData/fadeInDuration": fadeInDuration,
            "blendingControlData/fadeOutDuration": fadeOutDuration,
            "blendingControlData/onEventId": onEventId,
            "blendingControlData/offEventId": offEventId,
            "blendingControlData/onByDefault": onByDefault,
            "blendingControlData/fadeInOutCurve": fadeInOutCurve,
        }

        return self.new_record(
            "hkbLayer",
            object_id=object_id,
            useMotion=useMotion,
            **blend_params,
            **kwargs,
        )

    # Some typical chains
    def create_state_chain(
        self,
        state_id: int,
        animation: Animation | str | int,
        name: str,
        *,
        clip_mode: PlaybackMode = PlaybackMode.SINGLE_PLAY,
        state_transitions: HkbRecord | str = None,
        cmsg_name: str = None,
        enableScript: bool = True,
        enableTae: bool = True,
        offsetType: CmsgOffsetType = CmsgOffsetType.NONE,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        checkAnimEndSlotNo: int = -1,
        **cmsg_kwargs,
    ) -> tuple[HkbRecord, HkbRecord, HkbRecord]:
        transitions = self.get_record(state_transitions)

        clip = self.new_clip(animation, mode=clip_mode)
        cmsg = self.new_cmsg(
            name=cmsg_name or name + "_CMSG",
            animId=animation,
            generators=[clip],
            enableScript=enableScript,
            enableTae=enableTae,
            offsetType=offsetType,
            animeEndEventType=animeEndEventType,
            checkAnimEndSlotNo=checkAnimEndSlotNo,
            **cmsg_kwargs,
        )
        state = self.new_statemachine_state(
            stateId=state_id,
            name=name,
            generator=cmsg,
            transitions=transitions.object_id if transitions else None,
        )

        return (state, cmsg, clip)

    def create_blend_chain(
        self,
        clip: HkbRecord | str,
        animation: Animation | str | int,
        cmsg_name: str = None,
        *,
        blend_weight: int = 1,
        enableScript: bool = True,
        enableTae: bool = True,
        offsetType: CmsgOffsetType = CmsgOffsetType.NONE,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        checkAnimEndSlotNo: int = -1,
        **cmsg_kwargs,
    ) -> tuple[HkbRecord, HkbRecord]:
        cmsg = self.new_cmsg(
            name=cmsg_name,
            animId=animation,
            generators=[clip],
            enableScript=enableScript,
            enableTae=enableTae,
            offsetType=offsetType,
            animeEndEventType=animeEndEventType,
            checkAnimEndSlotNo=checkAnimEndSlotNo,
            **cmsg_kwargs,
        )
        blend = self.new_blender_generator_child(cmsg, weight=blend_weight)

        return (blend, cmsg)
