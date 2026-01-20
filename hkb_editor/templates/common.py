from typing import Any
import os
import re
import logging
from dataclasses import dataclass

from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray, HkbPointer
from hkb_editor.hkb.hkb_enums import (
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    CustomManualSelectorGenerator_ChangeTypeOfSelectedIndexAfterActivate as ChangeIndexType,
    CustomManualSelectorGenerator_RideSync as RideSync,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    hkbBlendCurveUtils_BlendCurve as BlendCurve,
    hkbVariableInfo_VariableType as VariableType,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfoArray_Flags as TransitionInfoFlags,
    hkbLayerGenerator_Flags as LayerGeneratorFlags,
)


@dataclass
class Variable:
    index: int
    name: str

    def __eq__(self, other: Any):
        return str(other) == str(self)

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return f"Variable '{self.name}' ({self.index})"


@dataclass
class Event:
    index: int
    name: str

    def __eq__(self, other: Any):
        return str(other) == str(self)

    def __str__(self):
        return self.name

    def __repr__(self) -> str:
        return f"Event '{self.name}' ({self.index})"


@dataclass
class Animation:
    index: int
    name: str
    full_name: str

    @classmethod
    def make_name(cls, category: int, anim_id: int) -> str:
        return f"a{category:03d}_{anim_id:06d}"

    @classmethod
    def is_valid_name(cls, name: str) -> bool:
        return bool(re.match(r"a[0-9]{3}_[0-9]{6}", name))

    @property
    def category(self) -> int:
        """the X part of aXXX_YYYYYY without leading zeros."""
        return int(self.name.split("_")[0][1:])

    @property
    def anim_id(self) -> int:
        """The Y part of aXXX_YYYYYY without leading zeros."""
        return int(self.name.split("_")[-1])

    def __eq__(self, other: Any):
        return str(other) == str(self)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Animation '{self.name}' ({self.index})"


# TODO record spec like this maybe?
# from typing import Annotated
# HkbRecordSpec = Annotated[HkbRecord, "type_name:CMSG"]


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
        if name == "logger":
            logger = logging.getLogger(os.path.basename(self._behavior.file))
            object.__setattr__(self, "logger", logger)
            return logger
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def variable(
        self,
        variable: Variable | str | int,
        *,
        var_type: VariableType = VariableType.INT32,
        range_min: int = 0,
        range_max: int = 0,
        default: Any = 0,
        create: bool = True,
    ) -> Variable:
        """Get a variable by name, or create it if it doesn't exist yet.

        Variables are typically used to control behaviors from other subsystems like HKS and TAE. See [CommonActionsMixin.bind_variable][] for the most common use case.

        Parameters
        ----------
        variable : str
            The name of the variable.
        var_type : VariableType, optional
            The type of data that will be stored in the variable.
        range_min : int, optional
            Minimum allowed value.
        range_max : int, optional
            Maximum allowed value.
        create : bool, optional
            If True create a new variable if it cannot be resolved.

        Returns
        -------
        Variable
            Description of the generated variable.
        """
        try:
            if isinstance(variable, Variable):
                return variable
            elif isinstance(variable, str):
                idx = self._behavior.find_variable(variable)
            elif isinstance(variable, int):
                idx = variable
                variable = self._behavior.get_variable(idx)
            else:
                raise TypeError(f"Invalid variable type {variable}")
        except ValueError:
            if not create:
                raise

            if not isinstance(variable, str):
                raise ValueError(f"Cannot create new variable from {variable}")

            var_type = VariableType(var_type)
            var = (variable, var_type, range_min, range_max, default)
            idx = self._behavior.create_variable(*var)
            self.logger.debug(
                f"Created new variable {variable} ({idx}) with type {var_type.name}"
            )

        return Variable(idx, variable)

    def event(self, event: Event | str | int, *, create: bool = True) -> Event:
        """Get the event with the specified name, or create it if it doesn't exist yet.

        Events are typically used to trigger transitions between statemachine states. See [get_next_state_id][] for details.
        TODO mention events.txt

        Parameters
        ----------
        event : str
            The name of the event to create. Typically starts with `W_`.
        create : bool, optional
            If True create a new variable if it cannot be resolved.

        Returns
        -------
        Event
            The generated event.
        """
        try:
            if isinstance(event, Event):
                return event
            elif isinstance(event, str):
                idx = self._behavior.find_event(event)
            elif isinstance(event, int):
                idx = event
                event = self._behavior.get_event(idx)
            else:
                raise TypeError(f"Invalid event type {event}")
        except ValueError:
            if not create:
                raise

            if not isinstance(event, str):
                raise ValueError(f"Cannot create new event from {event}")

            idx = self._behavior.create_event(event)
            self.logger.debug(f"Created new event {event} ({idx})")

        return Event(idx, event)

    def animation(
        self, animation: Animation | str | int, create: bool = True
    ) -> Animation:
        """Get the animation with the specified name, or create a new one if it doesn't exist yet.

        Animation names must follow the pattern `aXXX_YYYYYY`. Animation names are typically associated with one or more CustomManualSelectorGenerators (CMSG). See [new_cmsg][] for details.

        TODO mention animations.txt

        Parameters
        ----------
        animation : str
            The name of the animation slot following the `aXXX_YYYYYY` pattern.
        create : bool, optional
            If True create a new variable if it cannot be resolved.

        Returns
        -------
        Animation
            The generated animation name. Note that the full name is almost never used.
        """
        try:
            if isinstance(animation, Animation):
                return animation
            elif isinstance(animation, str):
                idx = self._behavior.find_animation(animation)
            elif isinstance(animation, int):
                idx = animation
                animation = self._behavior.get_animation(idx)
            else:
                raise TypeError(f"Invalid animation type {animation}")
        except ValueError:
            if not create:
                raise

            if not isinstance(animation, str):
                raise ValueError(f"Cannot create new animation from {animation}")

            if not re.fullmatch(r"a[0-9]{3}_[0-9]{6}", animation):
                raise ValueError(f"Invalid animation name '{animation}'")

            idx = self._behavior.create_animation(animation)
            self.logger.debug(f"Created new animation {animation} ({idx})")

        full_name = self._behavior.get_animation(idx, full_name=True)
        return Animation(idx, animation, full_name)

    def resolve_object(self, reference: Any, default: Any = None) -> HkbRecord:
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
            if state:
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
        var_idx = self.variable(variable).index

        with self._behavior.transaction():
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
                binding_set_ptr.set_value(binding_set)
            else:
                binding_set = binding_set_ptr.get_target()

            bindings: HkbArray = binding_set["bindings"]
            for bind in bindings:
                if bind["memberPath"] == path:
                    # Binding for this path already exists, update it
                    bound_var_idx = bind["variableIndex"]
                    bound_var_idx.set_value(var_idx)
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
                bindings.pop(idx)

    def new_record(
        self,
        object_type_name: str,
        object_id: str,
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
            self._behavior,
            type_id,
            kwargs,
            object_id=object_id,
        )
        if record.object_id:
            self._behavior.add_object(record)

        self.logger.debug(f"Created new {record}")

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
        source = self.resolve_object(source)

        if not source.object_id and object_id == "<new>":
            # Looks like an object that shouldn't be at the top level
            object_id = None

        attributes = {k: v.get_value() for k, v in source.get_value().items()}
        attributes.update(**overrides)

        return self.new_record(source.type_name, object_id, **attributes)

    def copy_attributes(
        self,
        source: HkbRecord | str,
        dest: HkbRecord | str,
        *attributes,
        allow_type_mismatch: bool = False,
    ) -> None:
        """Copy all attributes from the source record to the destination record.

        Parameters
        ----------
        source : HkbRecord | str
            The record to read attributes from.
        dest : HkbRecord | str
            The record to write attributes to.
        allow_type_mismatch : bool, optional
            If False, the source and destination record types must match exactly.

        Raises
        ------
        ValueError
            If allow_type_mismatch is False and the source and destination record types mismatch.
        """
        source = self.resolve_object(source)
        dest = self.resolve_object(dest)

        if allow_type_mismatch and source.type_id != dest.type_id:
            raise ValueError(
                f"Types don't match ({source.type_name} vs {dest.type_name})"
            )

        with self._behavior.transaction():
            for attr in attributes:
                src_attr = source.get_field(attr)
                new_val = src_attr.get_value()

                dest_attr = dest.get_field(attr)
                dest_attr.set_value(new_val)

    # Offer common defaults and highlight required settings for the most common objects
    # TODO document functions and their arguments

    def new_cmsg(
        self,
        animId: int | Animation,
        *,
        object_id: str = "<new>",
        name: str = "",
        generators: list[HkbRecord | str] = None,
        enableScript: bool = True,
        enableTae: bool = True,
        offsetType: CmsgOffsetType = CmsgOffsetType.NONE,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        changeTypeOfSelectedIndexAfterActivate: ChangeIndexType = ChangeIndexType.NONE,
        checkAnimEndSlotNo: int = -1,
        rideSync: RideSync = RideSync.DISABLE,
        isBasePoseAnim: bool = True,
        **kwargs,
    ) -> HkbRecord:
        """Create a new CustomManualSelectorGenerator (CMSG). A CMSG selects the generator to activate based on the state of the character, e.g. equipped skill, magic, or idle stance.

        Parameters
        ----------
        animId : int | Animation
            ID of animations this CMSG will handle (the Y part of aXXX_YYYYYY). All attached ClipGenerators should use this animation ID.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        name : str, optional
            The name of the new object.
        generators : list[HkbRecord  |  str], optional
            The generators this CMSG may choose from.
        enableScript : bool, optional
            ?unknown?
        enableTae : bool, optional
            Does this CMSG have actual animations associated?
        offsetType : CmsgOffsetType, optional
            How to choose the generator index to activate.
        animeEndEventType : AnimeEndEventType, optional
            What to do once the activated generator finishes.
        changeTypeOfSelectedIndexAfterActivate : ChangeIndexType, optional
            What to do when the generator index changes while already active.
        checkAnimEndSlotNo : int, optional
            ?unknown?
        rideSync : RideSync, optional
            Related to torrent, only present in Elden Ring.
        isBasePoseAnim : bool, optional
            Related to nightfarer animation layers, only present in Nightreign.
        kwargs : dict, optional
            Additional attributes for the record.

        Returns
        -------
        HkbRecord
            The created CMSG record.
        """
        if generators:
            generators = [self.resolve_object(obj).object_id for obj in generators]
        else:
            generators = []

        if isinstance(animId, Animation):
            animId = animId.anim_id

        return self.new_record(
            "CustomManualSelectorGenerator",
            object_id,
            name=name,
            generators=generators,
            offsetType=offsetType,
            animId=animId,
            enableScript=enableScript,
            enableTae=enableTae,
            checkAnimEndSlotNo=checkAnimEndSlotNo,
            animeEndEventType=animeEndEventType,
            changeTypeOfSelectedIndexAfterActivate=changeTypeOfSelectedIndexAfterActivate,
            rideSync=rideSync,
            isBasePoseAnim=isBasePoseAnim,
            **kwargs,
        )

    def new_manual_selector(
        self,
        variable: Variable | str | int,
        *,
        object_id: str = "<new>",
        name: str = "",
        generators: list[HkbRecord | str] = None,
        selectedGeneratorIndex: int = 0,
        variableBindingSet: HkbRecord | str = None,
        generatorChangedTransitionEffect: HkbRecord | str = None,
        selectedIndexCanChangeAfterActivate: bool = False,
        **kwargs,
    ) -> HkbRecord:
        """Creates a new ManualSelectorGenerator (MSG). The generator to activate is typically controlled by binding the `selectedGeneratorIndex` to a variable, which is then set from hks using `SetVariable()`.

        Parameters
        ----------
        variable : Variable | str | int
            Variable to bind the selectedGeneratorIndex to. Set to None if you don't want to bind it yet.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        name : str, optional
            The name of the new object.
        generators : list[HkbRecord  |  str], optional
            The generators this MSG may choose from. First generator will be 0.
        selectedGeneratorIndex : int, optional
            Initial value of the selected generator.
        variableBindingSet : HkbRecord | str, optional
            Set this if you want to reuse an already existing variable binding.
        generatorChangedTransitionEffect : HkbRecord | str, optional
            Transition effect to use when the generator index changes while active.
        selectedIndexCanChangeAfterActivate : bool, optional
            Whether the active generator index is allowed to change while active.
        kwargs : dict, optional
            Additional attributes for the record.

        Returns
        -------
        HkbRecord
            The created MSG record.
        """
        if generators:
            generators = [self.resolve_object(obj).object_id for obj in generators]
        else:
            generators = []

        variableBindingSet = self.resolve_object(variableBindingSet)
        generatorChangedTransitionEffect = self.resolve_object(
            generatorChangedTransitionEffect
        )

        kwargs.setdefault("sentOnClipEnd/id", -1)
        kwargs.setdefault("endOfClipEventId", -1)

        selector = self.new_record(
            "hkbManualSelectorGenerator",
            object_id,
            name=name,
            generators=generators,
            selectedGeneratorIndex=selectedGeneratorIndex,
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
        """Create a new ClipGenerator. These nodes are responsible for running TAE animations.

        Parameters
        ----------
        animation : Animation | str | int
            The animation to execute.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        name : str, optional
            The name of the new object.
        playbackSpeed : int, optional
            Multiplicative factor for the animation's playback speed.
        mode : PlaybackMode, optional
            How to play the animation.
        kwargs : dict, optional
            Additional attributes for the record.

        Returns
        -------
        HkbRecord
            The new hkbClipGenerator record.
        """
        animation = self.animation(animation)

        if name is None:
            name = animation.name

        return self.new_record(
            "hkbClipGenerator",
            object_id,
            name=name,
            animationName=animation.name,
            playbackSpeed=playbackSpeed,
            animationInternalId=animation.index,
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
        """Create a new statemachine state.

        Every statemachine can have only one state active at a time. However, it is possible to have multiple statemachines active by using layered animations (e.g. blending or half blends, see [new_blender_generator][] and [new_layer_generator][]).

        FromSoft usually uses wildcard transitions, i.e. every state can transition to any state within the same statemachine with no prior conditions. However, states may also define dedicated transitions to other states.

        Parameters
        ----------
        stateId : int
            ID of the state. State IDs must be unique within their statemachine. See [get_next_state_id][] to generate a new valid ID.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        name : str, optional
            The name of the new object.
        transitions : HkbRecord | str, optional
            Custom transitions to other states.
        generator : HkbRecord | str, optional
            The generator this state will activate. Usually a CMSG or MSG, but any type of generator is valid, including a statemachine.
        probability : float, optional
            Probability weight to activate this state when the statemachine chooses a state at random.
        enable : bool, optional
            Whether this state can be activated.

        Returns
        -------
        HkbRecord
            The new hkbStateMachine::StateInfo record.
        """
        transitions = self.resolve_object(transitions)
        generator = self.resolve_object(generator)

        return self.new_record(
            "hkbStateMachine::StateInfo",
            object_id,
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
        """An object for defining possible transitions to other states within a statemachine.

        Parameters
        ----------
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        transitions : list[HkbRecord], optional
            List of possible transitions. See [new_transition_info][] to generate these.

        Returns
        -------
        HkbRecord
            The new hkbStateMachine::TransitionInfoArray record.
        """
        return self.new_record(
            "hkbStateMachine::TransitionInfoArray",
            object_id,
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
        """Defines a transition from the active state to another.

        Parameters
        ----------
        toStateId : int
            ID of the state to transition to.
        eventId : Event | str | int
            The event that will activate this transition (if the owning object is active).
        transition : HkbRecord | str, optional
            Blending effect to use when this transition becomes active. Often empty or the default transition (see [get_default_transition_effect][]).
        flags : TransitionInfoFlags, optional
            Additional flags for this transition.

        Returns
        -------
        HkbRecord
            The new hkbStateMachine::TransitionInfo record.
        """
        eventId = self.event(eventId)

        if not transition:
            transition = self.get_default_transition_effect()
        else:
            transition = self.resolve_object(transition)

        kwargs.setdefault("triggerInterval/enterEventId", -1)
        kwargs.setdefault("triggerInterval/exitEventId", -1)
        kwargs.setdefault("initiateInterval/enterEventId", -1)
        kwargs.setdefault("initiateInterval/exitEventId", -1)

        return self.new_record(
            "hkbStateMachine::TransitionInfo",
            None,  # Not a top-level object
            toStateId=toStateId,
            eventId=eventId.index,
            transition=transition.object_id if transition else None,
            flags=flags,
            **kwargs,
        )

    def new_blender_generator(
        self,
        children: list[HkbRecord | str],
        *,
        object_id: str = "<new>",
        name: str = "",
        blendParameter: float = 1.0,
        minCyclicBlendParameter: float = 0.0,
        maxCyclicBlendParameter: float = 1.0,
        indexOfSyncMasterChild: int = -1,
        **kwargs,
    ) -> HkbRecord:
        """Generator object for handling animation blending (transitioning from one animation to another).

        Parameters
        ----------
        children : list[HkbRecord  |  str]
            Blending children, see [new_blender_generator_child][].
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        name : str, optional
            The name of the new object.
        blendParameter : float, optional
            How far the blending has progressed. Typically bound to a variable and controlled from HKS or TAE.
        minCyclicBlendParameter : float, optional
            ?unknown?
        maxCyclicBlendParameter : float, optional
            ?unknown?
        indexOfSyncMasterChild : int, optional
            ?unknown?

        Returns
        -------
        HkbRecord
            The new hkbBlenderGenerator record.
        """
        children = [self.resolve_object(c) for c in children]

        return self.new_record(
            "hkbBlenderGenerator",
            object_id,
            name=name,
            children=children,
            blendParameter=blendParameter,
            minCyclicBlendParameter=minCyclicBlendParameter,
            maxCyclicBlendParameter=maxCyclicBlendParameter,
            indexOfSyncMasterChild=indexOfSyncMasterChild,
            **kwargs,
        )

    def new_blender_generator_child(
        self,
        generator: HkbRecord | str,
        *,
        object_id: str = "<new>",
        weight: float = 1.0,
        worldFromModelWeight: int = 1,
        **kwargs,
    ) -> HkbRecord:
        """A child object that can be attached to a BlenderGenerator ([new_blender_generator][]).

        Parameters
        ----------
        generator : HkbRecord | str
            The generator to activate as this blend layer is weighted more.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        weight : float, optional
            Weight of this blend layer compared to siblings.
        worldFromModelWeight : int, optional
            ?unknown?

        Returns
        -------
        HkbRecord
            The new hkbBlenderGeneratorChild record.
        """
        generator = self.resolve_object(generator)

        return self.new_record(
            "hkbBlenderGeneratorChild",
            object_id,
            generator=generator.object_id if generator else None,
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
        flags: LayerGeneratorFlags = LayerGeneratorFlags.NONE,
        **kwargs,
    ) -> HkbRecord:
        """Generator object for playing multiple animations at the same time (e.g. half blends).

        Parameters
        ----------
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        name : str, optional
            The name of the new object.
        layers : list[HkbRecord  |  str], optional
            Animation layers to activate. See [new_layer_generator_child][].
        indexOfSyncMasterChild : int, optional
            The child to use for synchronizing durations if SYNC is true.
        flags : LayerGeneratorFlags, optional
            Additional flags for this generator.

        Returns
        -------
        HkbRecord
            The new hkbLayerGenerator record.
        """
        if layers:
            layers = [self.resolve_object(x).object_id for x in layers]
        else:
            layers = []

        return self.new_record(
            "hkbLayerGenerator",
            object_id,
            name=name,
            layers=layers,
            indexOfSyncMasterChild=indexOfSyncMasterChild,
            flags=flags,
            **kwargs,
        )

    def new_layer_generator_child(
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
        """Creates a new animation layer. Should be attached to a LayerGenerator, see [new_layer_generator][].

        Parameters
        ----------
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        generator : HkbRecord | str, optional
            The actual animation generator to activate.
        boneWeights : HkbRecord | str, optional
            How much each bone of this animation will affect the end result.
        useMotion : bool, optional
            Set to true if this animation's world transform should be used (worldFromModel). Typically only active for one layer per LayerGenerator.
        weight : float, optional
            How much this layer affects the end result.
        fadeInDuration : float, optional
            Time over which this layer gradually becomes activates.
        fadeOutDuration : float, optional
            Time over which this layer gradually becomes deactivates.
        onEventId : Event | str | int, optional
            An event to switch on this layer.
        offEventId : Event | str | int, optional
            An event to switch off this layer.
        onByDefault : bool, optional
            Whether this layer should be active when its parent activates.
        fadeInOutCurve : BlendCurve, optional
            Curve to use when fading this layer in or out.

        Returns
        -------
        HkbRecord
            The new hkbLayer record.
        """
        generator = self.resolve_object(generator)
        boneWeights = self.resolve_object(boneWeights)
        onEventId = self.event(onEventId)
        offEventId = self.event(offEventId)

        blend_params = {
            "blendingControlData/weight": weight,
            "blendingControlData/fadeInDuration": fadeInDuration,
            "blendingControlData/fadeOutDuration": fadeOutDuration,
            "blendingControlData/onEventId": onEventId.index,
            "blendingControlData/offEventId": offEventId.index,
            "blendingControlData/onByDefault": onByDefault,
            "blendingControlData/fadeInOutCurve": fadeInOutCurve,
        }

        return self.new_record(
            "hkbLayer",
            object_id,
            generator=generator,
            boneWeights=boneWeights,
            useMotion=useMotion,
            **blend_params,
            **kwargs,
        )

    ###
    # Some typical tasks
    ###

    def get_default_transition_effect(self) -> HkbRecord:
        """Returns the most commonly linked CustomTransitionEffect. In Elden Ring and Nightreign this object will be called DefaultTransition.

        Note that for very small behaviors like enemies this may not return what you expect. If in doubt use [TemplateContext.find][] instead.

        Returns
        -------
        HkbRecord
            The most common transition effect object.
        """
        return self._behavior.get_most_common_object("CustomTransitionEffect")

    def create_state_chain(
        self,
        state_id: int,
        animation: Animation | str | int,
        name: str,
        *,
        state_kwargs: dict[str, Any] = None,
        cmsg_kwargs: dict[str, Any] = None,
        clip_kwargs: dict[str, Any] = None,
    ) -> tuple[HkbRecord, HkbRecord, HkbRecord]:
        """Creates one of the most common behavior structures in recent FromSoft titles: StateInfo -> CMSG -> ClipGenerator.

        Note that this chain will not be attached. You still have to append it to a statemachine's `states` (see [TemplateContext.array_add][]) and setup a transition (e.g. using [register_wildcard_transition][]).

        Parameters
        ----------
        state_id : int
            ID of the generated StateInfo.
        animation : Animation | str | int
            The animation to play.
        name : str
            A name to base the new objects' names on.
        state_kwargs : dict[str, Any], optional
            Additional attributes for the generated StateInfo.
        cmsg_kwargs : dict[str, Any], optional
            Additional attributes for the generated CMSG.
        clip_kwargs : dict[str, Any], optional
            Additional attributes for the generated ClipGenerator.

        Returns
        -------
        tuple[HkbRecord, HkbRecord, HkbRecord]
            The new hkbStateInfo, CustomManualSelectorGenerator and hkbClipGenerator records.
        """
        # ClipGenerator
        if clip_kwargs is None:
            clip_kwargs = {}

        animation = self.animation(animation)
        clip = self.new_clip(animation, **clip_kwargs)

        # CMSG
        if cmsg_kwargs is None:
            cmsg_kwargs = {}
        cmsg_kwargs.setdefault("name", name + "_CMSG")
        cmsg_kwargs.setdefault("generators", [clip])

        cmsg = self.new_cmsg(animation, **cmsg_kwargs)

        # StateInfo
        if state_kwargs is None:
            state_kwargs = {}
        state_kwargs.setdefault("name", name)
        state_kwargs.setdefault("generator", cmsg)

        state = self.new_statemachine_state(state_id, **state_kwargs)

        return (state, cmsg, clip)

    def create_blend_chain(
        self,
        animation: Animation | str | int,
        blend_weight: int = 1,
        cmsg_name: str = None,
        *,
        offsetType: CmsgOffsetType = CmsgOffsetType.IDLE_CATEGORY,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.NONE,
        cmsg_kwargs: dict[str, Any] = None,
    ) -> tuple[HkbRecord, HkbRecord, HkbRecord]:
        """Creates another common behavior structure, used for e.g. usable items and gestures: BlenderGeneratorChild -> CMSG -> ClipGenerator.

        This setup is typically used with a parametric blend BlenderGenerator, where blend_weight also acts as the ID of the generator. Make sure this ID is an integer and unique within the BlenderGenerator when using this setup!

        Parameters
        ----------
        animation : Animation | str | int
            Animation to use for the clip.
        blend_weight : int, optional
            Blend weight of the BlenderGeneratorChild.
        cmsg_name : str, optional
            Name of the CMSG, typically ends with "_CMSG".
        offsetType : CmsgOffsetType, optional
            Generator selection mode of the CMSG. Usually there's only one clip attached and this doesn't matter.
        animeEndEventType : AnimeEndEventType, optional
            What the CMSG should do once the activated generator finishes.

        Returns
        -------
        tuple[HkbRecord, HkbRecord, HkbRecord]
            The new hkbBlenderGeneratorChild, CustomManualSelectorGenerator, and hkbClipGenerator records.
        """
        clip = self.new_clip(animation)

        if cmsg_kwargs is None:
            cmsg_kwargs = {}
        cmsg_kwargs.setdefault("name", cmsg_name)
        cmsg_kwargs.setdefault("generators", [clip])
        cmsg_kwargs.setdefault(
            "offsetType",
            offsetType,
        )
        cmsg_kwargs.setdefault(
            "animeEndEventType",
            animeEndEventType,
        )

        cmsg = self.new_cmsg(animation.anim_id, **cmsg_kwargs)
        blend = self.new_blender_generator_child(cmsg, weight=blend_weight)

        return (blend, cmsg, clip)

    def register_wildcard_transition(
        self,
        statemachine: HkbRecord | str,
        toStateId: int,
        eventId: Event | str | int,
        *,
        transition_effect: HkbRecord | str = None,
        flags: TransitionInfoFlags = 3584,
        # ALLOW_SELF_TRANSITION_BY_TRANSITION_FROM_ANY_STATE,
        # IS_LOCAL_WILDCARD
        # IS_GLOBAL_WILDCARD
        **kwargs,
    ) -> None:
        """Sets up a wildcard transition for a given statemachine's state, i.e. a way to transition to this state from any other state.

        Parameters
        ----------
        statemachine : HkbRecord | str
            The statemachine to setup the wildcard transition for.
        toStateId : int
            ID of the target state.
        eventId : Event | str | int
            Event that activates this transition.
        transition_effect : HkbRecord | str, optional
            Effect to use when this transition activates. If None will use the [get_default_transition_effect][].
        flags : TransitionInfoFlags, optional
            Additional flags for this transition.
        """
        statemachine = self.resolve_object(statemachine)
        eventId = self.event(eventId)

        if not transition_effect:
            transition_effect = self.get_default_transition_effect()
        else:
            transition_effect = self.resolve_object(transition_effect)

        kwargs.setdefault("triggerInterval/enterEventId", -1)
        kwargs.setdefault("triggerInterval/exitEventId", -1)
        kwargs.setdefault("initiateInterval/enterEventId", -1)
        kwargs.setdefault("initiateInterval/exitEventId", -1)

        wildcards_ptr: HkbPointer = statemachine["wildcardTransitions"]
        if wildcards_ptr.is_set():
            wildcards = wildcards_ptr.get_target()
        else:
            wildcards = self.new_record(
                "hkbStateMachine::TransitionInfoArray",
                "<new>",
                transitions=[],
            )
            wildcards_ptr.set_value(wildcards)

        transitions: HkbArray = wildcards["transitions"]
        transitions.append(
            self.new_record(
                "hkbStateMachine::TransitionInfo",
                None,  # Not a top-level object
                toStateId=toStateId,
                eventId=eventId.index,
                transition=transition_effect,
                flags=flags,
                **kwargs,
            )
        )

    def add_wildcard_state(
        self,
        statemachine: HkbRecord | str,
        state: HkbRecord | str,
        event: Event | str = None,
        transition_effect: HkbRecord | str = None,
        copy_transition_effect: bool = False,
        flags: TransitionInfoFlags = 3584,
    ) -> HkbRecord:
        """Add a state to a statemachine and setup a wildcard transition for it.

        Goes really well with create_state_chain!

        Parameters
        ----------
        statemachine : HkbRecord | str
            The statemachine to add the state to.
        state : HkbRecord | str
            The state to add, which should not have been added elsewhere yet. Note that if this is a string a new state with that name will be created.
        event : Event | str, optional
            The wildcard transition event. If None, no wildcard transition will be setup.
        transition_effect : HkbRecord | str, optional
            The transition effect to use for the wildcard transition.
        copy_transition_effect : bool, optional
            If True and a transition effect is provided, a copy of the effect is created with a new name based on the event's name (which is how FS often does it).
        flags : TransitionInfoFlags, optional
            Flags of the transition.

        Returns
        -------
        HkbRecord
            The state that was added to the statemachine.
        """
        statemachine = self.resolve_object(statemachine)

        if isinstance(state, str):
            state_id = self.get_next_state_id(statemachine)
            state = self.new_statemachine_state(state_id)
        else:
            state_id = state["stateId"].get_value()

        statemachine["states"].append(state)

        if event:
            if copy_transition_effect and transition_effect:
                transition_effect = self.make_copy(
                    transition_effect, name=self.event(event).name
                )

            self.register_wildcard_transition(
                statemachine,
                state_id,
                event,
                transition_effect=transition_effect,
                flags=flags,
            )

        return state
