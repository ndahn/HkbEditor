from typing import Any, Type, Literal
from dataclasses import dataclass
import ast
from docstring_parser import parse as parse_docstring, DocstringParam
import re

from hkb_editor.gui.workflows.undo import undo_manager
from hkb_editor.hkb import HavokBehavior, HkbRecord, HkbArray
from hkb_editor.hkb.hkb_enums import (
    hkbVariableInfo_VariableType as VariableType,
    CustomManualSelectorGenerator_OffsetType as CmsgOffsetType,
    CustomManualSelectorGenerator_AnimeEndEventType as AnimeEndEventType,
    hkbClipGenerator_PlaybackMode as PlaybackMode,
    hkbBlendCurveUtils_BlendCurve as BlendCurve,
)
from hkb_editor.hkb.hkb_flags import (
    hkbStateMachine_TransitionInfo_Flags as TransitionInfoFlags,
)
from hkb_editor.hkb.utils import get_object, get_next_state_id, bind_variable


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


@dataclass
class HkbRecordSpec:
    query: str = None
    type_name: str = None


_undefined = object()


class TemplateContext:
    """Stores information and provides helper functions for temapltes.
    
    Templates are python scripts with a `run` function that takes a `TemplateContext` as their first argument. This object should be the main way of modifying the behavior from templates, primarily to give proper support for undo (or rollback in case of errors).

    Raises
    ------
    SyntaxError
        If the template does not contain valid python code.
    ValueError
        If the template is not a valid template file.
    """
    @dataclass
    class _Arg:
        name: str
        type: Type
        value: Any = None
        doc: str = None

    def __init__(self, behavior: HavokBehavior, template_file: str):
        self._behavior = behavior
        self._template_file = template_file
        self._template_func: ast.FunctionDef = None

        self._title: str = None
        self._description: str = None
        self._args: dict[str, TemplateContext._Arg] = {}

        tree = ast.parse(open(template_file).read(), template_file, mode="exec")

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                self._template_func = node
                self._parse_template_func(node)
                break
        else:
            raise ValueError("Template does not contain a run() function")

    def _parse_template_func(self, func: ast.FunctionDef):
        doc = parse_docstring(ast.get_docstring(func))
        self._title = doc.short_description
        self._description = doc.long_description

        def type_from_str(type_str: str) -> type:
            if type_str.startswith("Literal["):
                # Python 3.9+
                choices = ast.literal_eval(type_str[7:])
                return Literal[tuple(choices)]

            valid = {
                c.__name__: c
                for c in (
                    int,
                    float,
                    bool,
                    str,
                    Variable,
                    Event,
                    Animation,
                    HkbRecord,
                    TemplateContext,
                )
            }
            return valid[type_str]

        def get_arg_type(arg: ast.arg, arg_doc: DocstringParam, default: Any):
            if arg.annotation:
                return type_from_str(ast.unparse(arg.annotation))
            elif arg_doc:
                return type_from_str(arg_doc.type_name)
            elif default is not None:
                return type(default)
            else:
                raise ValueError(f"Type of argument {name} could not be determined")

        def collect_args(args: list[ast.arg], defaults: list[Any]):
            # defaults are specified from the right
            pad = [None] * (len(args) - len(defaults))

            for arg, arg_default in zip(args, pad + defaults):
                name = arg.arg

                default = None
                if arg_default is not None:
                    try:
                        default = ast.literal_eval(arg_default)
                    except ValueError:
                        default = str(arg_default)

                arg_doc = next((p for p in doc.params if p.arg_name == name), None)
                arg_type = get_arg_type(arg, arg_doc, default)

                if arg_type == TemplateContext:
                    continue

                self._args[name] = TemplateContext._Arg(
                    name,
                    arg_type,
                    default,
                    arg_doc.description if arg_doc else "",
                )

        collect_args(func.args.args, func.args.defaults)
        collect_args(func.args.kwonlyargs, func.args.kw_defaults)

    def find_all(self, query: str) -> list[HkbRecord]:
        """Returns all objects matching the specified query. 
        
        Parameters
        ----------
        query : str
            The query string. See :py:meth:`hkb.Tagfile.query` for details.

        Returns
        -------
        list[HkbRecord]
            A list of matching :py:class:`HkbRecord` objects.
        """
        return list(self._behavior.query(query))

    def find(self, query: str, default: Any = _undefined) -> HkbRecord:
        """Returns the first object matching the specified query. 
        
        Parameters
        ----------
        query : str
            The query string. See :py:meth:`hkb.Tagfile.query` for details.
        default : Any
            The value to return if no match is found. 

        Raises
        ------
        KeyError
            If no match was found and no default was provided.

        Returns
        -------
        HkbRecord
            A matching :py:class:`HkbRecord` object.
        """
        try:
            return next(self._behavior.query(query))
        except StopIteration:
            if default != _undefined:
                return default

            raise KeyError(f"No object matching '{query}'")

    # TODO remove?
    def get(
        self,
        record: HkbRecord | str,
        path: str,
        default: Any = None,
    ) -> Any:
        """Retrieve a value from the specified :py:class:`HkbRecord`.

        Parameters
        ----------
        record : HkbRecord | str
            The record to retrieve a value from.
        path : str
            Member path to the value of interest with deeper levels separated by /.
        default : Any, optional
            A default to return if the path doesn't exist.

        Raises
        ------
        KeyError
            If the specified path does not exist.

        Returns
        -------
        Any
            The value resolved to a regular type (non-recursive).
        """
        record = get_object(self._behavior, record)
        return record.get_path_value(path, default=default, resolve=True)

    def set(self, record: HkbRecord | str, **attributes) -> None:
        """Update a one or more fields of the specified :py:class:`HkbRecord`.

        Parameters
        ----------
        record : HkbRecord | str
            The record to update.
        attributes : dict[str, Any]
            Keyword arguments of fields and values to set.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        with undo_manager.combine():
            for path, value in attributes.items():
                handler = record.get_path_value(path)
                handler.set_value(value)
                undo_manager.on_update_value(handler, handler.get_value(), value)

    def delete(self, record: HkbRecord | str) -> HkbRecord:
        """Delete the specified :py:class:`HkbRecord` from the behavior.

        Parameters
        ----------
        record : HkbRecord | str
            The record to delete.

        Returns
        -------
        HkbRecord
            The record that was deleted.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        if record.object_id:
            self._behavior.objects.pop(record.object_id)
            undo_manager.on_delete_object(record)
            return record

        return None

    def array_add(self, record: HkbRecord | str, path: str, item: Any) -> None:
        """Append a value to an array field of the specified record.

        Note that when appending to pointer arrays you need to pass an object ID, not an actual object.

        Parameters
        ----------
        record : HkbRecord | str
            The record holding the array.
        path : str
            Path to the array within the record, with deeper levels separated by /.
        item : Any
            The item to append to the array.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        array: HkbArray = record.get_path_value(path)
        array.append(item)
        undo_manager.on_update_array_item(array, -1, None, item)

    def array_pop(self, record: HkbRecord | str, path: str, index: int = -1) -> Any:
        """Remove a value from an array inside a record.

        Parameters
        ----------
        record : HkbRecord | str
            The record holding the array.
        path : str
            Path to the array within the record, with deeper levels separated by /.
        index : int
            The index of the item to pop.

        Returns
        -------
        Any
            The value that was removed from the array.
        """
        if isinstance(record, str):
            record = self._behavior[record]

        array: HkbArray = record.get_path_value(path)
        ret = array.pop(index).get_value()
        undo_manager.on_update_array_item(array, index, ret, None)
        return ret

    def free_state_id(self, statemachine: HkbRecord | str) -> int:
        """Find the next free stateId in a hkbStatemachine and return it.

        Parameters
        ----------
        statemachine : HkbRecord | str
            The hkbStatemachine to search.

        Returns
        -------
        int
            A state ID one higher than the largest stateId already in use.
        """
        statemachine = get_object(self._behavior, self._behavior, statemachine)
        return get_next_state_id(statemachine)

    def bind_variable(
        self,
        obj: HkbRecord | str,
        path: str,
        variable: Variable | str | int,
    ) -> HkbRecord:
        """Bind a record field to a variable. 
        
        This allows to control aspects of a behavior object through HKS or TAE. Most commonly used for ManualSelectorGenerators. Note that in HKS variables are referenced by their name, in all other places the variables' indices are used. 

        If the record does not have a variableBindingSet yet it will be created. If the record already has a binding for the specified path it will be updated to the provided variable.

        Parameters
        ----------
        obj : HkbRecord | str
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
        obj = get_object(self._behavior, obj)

        if isinstance(variable, Variable):
            variable = variable.index

        return bind_variable(self._behavior, obj, path, variable)

    def new_variable(
        self,
        name: str,
        data_type: VariableType = VariableType.INT32,
        range_min: int = 0,
        range_max: int = 0,
    ) -> Variable:
        """Create a new variable. 
        
        Variables are typically used to control behaviors from other subsystems like HKS and TAE. See :py:meth:`bind_attribute` for the most common use case.

        Parameters
        ----------
        name : str
            The name of the variable. Must not exist yet.
        data_type : VariableType, optional
            The type of data that will be stored in the variable.
        range_min : int, optional
            Minimum allowed value.
        range_max : int, optional
            Maximum allowed value.

        Returns
        -------
        Variable
            Description of the generated variable.
        """
        idx = self._behavior.create_variable(name, data_type, range_min, range_max)
        undo_manager.on_create_variable(self._behavior, name)
        return Variable(idx, name)

    def get_variable(self, name: str) -> Variable:
        """Retrieve an already existing variable by name.

        Parameters
        ----------
        name : str
            The name of the variable you are looking for.

        Raises
        ------
        IndexError
            If no variable with the specified name can be found.

        Returns
        -------
        Variable
            The variable with the specified name.
        """
        return Variable(self._behavior.find_variable(name), name)

    def new_event(self, event: str) -> Event:
        """Create a new event. 
        
        Events are typically used to trigger transitions between statemachine states. See :py:meth:`new_statemachine_state` for details.
        TODO mention events.txt

        Parameters
        ----------
        event : str
            The name of the event to create. Typically starts with `W_`.

        Returns
        -------
        Event
            The generated event.
        """
        idx = self._behavior.create_event(event)
        undo_manager.on_create_event(self._behavior, event)
        return Event(idx, event)

    def get_event(self, name: str) -> Event:
        """Retrieve an event based on its name.

        Parameters
        ----------
        name : str
            The name of the event.

        Raises
        ------
        IndexError
            If no event with the specified name can be found.

        Returns
        -------
        Event
            The event with the specified name.
        """
        return Event(self._behavior.find_event(name), name)

    def new_animation(self, animation: str) -> Animation:
        """Generate a new entry for an animation slot.

        Animation names must follow the pattern `aXXX_YYYYYY`. Animation names are typically associated with one or more CustomManualSelectorGenerators (CMSG). See :py:meth:`new_cmsg` for details.
        # TODO mention animations.txt

        Parameters
        ----------
        animation : str
            The name of the animation slot following the `aXXX_YYYYYY` pattern.

        Returns
        -------
        Animation
            The generated animation name. Note that the full name is almost never used.
        """
        if not re.fullmatch(r"a[0-9]{3}_[0-9]{6}"):
            raise ValueError(f"Invalid animation name '{animation}'")

        idx = self._behavior.create_animation(animation)
        undo_manager.on_create_animation(self._behavior, animation)
        return Animation(
            idx,
            self._behavior.get_animation(idx, full_name=False),
            self._behavior.get_animation(idx, full_name=True),
        )

    def get_animation(self, short_name: str) -> Animation:
        """Retrieve an animation slot based on its name.

        Parameters
        ----------
        short_name : str
            The name of the animation following the `aXXX_YYYYYY` pattern.

        Returns
        -------
        Animation
            The animation with the specified short name.
        """
        idx = self._behavior.find_event(short_name)
        full_name = self._behavior.get_animation(idx, full_name=True)
        return Animation(idx, short_name, full_name)

    def new(
        self,
        object_type_name: str,
        *,
        object_id: str = "<new>",
        **kwargs: Any,
    ) -> HkbRecord:
        """Create an arbitrary new hkb object. If an object ID is provided or generated, the object will also be added to the behavior.

        Parameters
        ----------
        object_type_name : str
            The type of the object to generate. In decompiled hkb this is usually the comment under the `<object id="..." typeid="...">` line.
        object_id : str, optional
            The object ID the record should use. Create a new ID if "<new>" is passed.
        kwargs:
            Any fields you want to set for the generated object. Fields not specified will use their type default (e.g. int will be 0, str will be empty, etc.).

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

        return record

    def make_copy(
        self,
        source: HkbRecord | str,
        *,
        object_id: str = "<new>",
        **overrides
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
        source = get_object(source)

        attributes = {k:v.get_value() for k,v in source.get_value().items()}
        attributes.update(**overrides)

        return self.new(
            source.type_name,
            object_id=object_id,
            **attributes
        )

    # Offer common defaults and highlight required settings for the most common objects
    # TODO document functions and their arguments

    def new_cmsg(
        self,
        *,
        object_id: str = "<new>",
        name: str = "",
        animId: Animation | int | str = 0,
        generators: list[HkbRecord | str] = None,
        enableScript: bool = True,
        enableTae: bool = True,
        offsetType: CmsgOffsetType = CmsgOffsetType.NONE,
        animeEndEventType: AnimeEndEventType = AnimeEndEventType.FIRE_NEXT_STATE_EVENT,
        checkAnimEndSlotNo: int = -1,
        **kwargs,
    ) -> HkbRecord:
        if isinstance(animId, Animation):
            animId = animId.name

        if isinstance(animId, str):
            # Assume it's an animation name
            animId = int(animId.split("_")[-1])

        if generators:
            generators = [
                get_object(self._behavior, obj).object_id for obj in generators
            ]
        else:
            generators = []

        return self.new(
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
            **kwargs,
        )

    def new_selector(
        self,
        variable: Variable | int | str,
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
            generators = [get_object(self._behavior, obj).object_id for obj in generators]
        else:
            generators = []

        variableBindingSet = get_object(self._behavior, variableBindingSet)
        generatorChangedTransitionEffect = get_object(
            self._behavior, generatorChangedTransitionEffect
        )

        kwargs.setdefault("sentOnClipEnd/id", -1)
        kwargs.setdefault("endOfClipEventId", -1)

        selector = self.new(
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
            # Sometimes we may just want to reuse an existing binding set
            if isinstance(variable, Variable):
                variable = variable.index

            # Will create a new binding set if necessary
            bind_variable(self._behavior, selector, "selectedGeneratorIndex", variable)

        return selector

    def new_clip(
        self,
        animation: Animation | int | str,
        *,
        object_id: str = "<new>",
        name: str = None,
        playbackSpeed: int = 1,
        mode: PlaybackMode = PlaybackMode.SINGLE_PLAY,
        **kwargs,
    ) -> HkbRecord:
        if isinstance(animation, Animation):
            anim_name = animation.name
            anim_id = animation.index
        elif isinstance(animation, int):
            anim_name = self._behavior.get_animation(animation)
            anim_id = animation
        else:
            anim_name = animation
            anim_id = self._behavior.find_animation(animation)

        if name is None:
            name = anim_name

        return self.new(
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
        transition = get_object(self._behavior, transition)
        generator = get_object(self._behavior, generator)

        return self.new(
            "hkbStateMachine::StateInfo",
            object_id=object_id,
            stateId=stateId,
            name=name,
            transitions=transitions.object_id if transition else None,
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
        return self.new(
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
        if transition is None:
            transition = next(self._behavior.query("name:DefaultTransition"), None)

        if isinstance(eventId, Event):
            eventId = eventId.index
        elif isinstance(eventId, str):
            eventId = self._behavior.find_event(eventId)

        kwargs.setdefault("triggerInterval/enterEventId", -1)
        kwargs.setdefault("triggerInterval/exitEventId", -1)
        kwargs.setdefault("initiateInterval/enterEventId", -1)
        kwargs.setdefault("initiateInterval/exitEventId", -1)

        return self.new(
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
        cmsg = get_object(self._behavior, cmsg)

        return self.new(
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
            layers = [get_object(self._behavior, l) for l in layers]
        else:
            layers = []

        return self.new(
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
        generator = get_object(generator)
        boneWeights = get_object(boneWeights)

        if isinstance(onEventId, Event):
            onEventId = onEventId.index
        elif isinstance(onEventId, str):
            onEventId = self._behavior.find_event(onEventId)

        if isinstance(offEventId, Event):
            offEventId = offEventId.index
        elif isinstance(offEventId, str):
            offEventId = self._behavior.find_event(offEventId)

        blend_params = {
            "blendingControlData/weight": weight,
            "blendingControlData/fadeInDuration": fadeInDuration,
            "blendingControlData/fadeOutDuration": fadeOutDuration,
            "blendingControlData/onEventId": onEventId,
            "blendingControlData/offEventId": offEventId,
            "blendingControlData/onByDefault": onByDefault,
            "blendingControlData/fadeInOutCurve": fadeInOutCurve,
        }

        return self.new(
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
        animation: Animation | int | str,
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
        transitions = get_object(self._behavior, state_transitions)

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
        animation: int | str,
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
