from typing import Any, Type, Literal
from dataclasses import dataclass
import ast
from docstring_parser import parse as parse_docstring, DocstringParam

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
        return list(self._behavior.query(query))

    def find(self, query: str, default: Any = _undefined) -> HkbRecord:
        try:
            return next(self._behavior.query(query))
        except StopIteration:
            if default != _undefined:
                return default

            raise KeyError(f"No object matching '{query}'")

    def get(
        self,
        record: HkbRecord | str,
        path: str,
        default: Any = None,
    ) -> Any:
        if isinstance(record, str):
            record = self._behavior[record]

        return record.get_path_value(path, default=default, resolve=True)

    def set(self, record: HkbRecord | str, **attributes) -> None:
        if isinstance(record, str):
            record = self._behavior[record]

        with undo_manager.combine():
            for path, value in attributes.items():
                handler = record.get_path_value(path)
                handler.set_value(value)
                undo_manager.on_update_value(handler, handler.get_value(), value)

    def delete(self, record: HkbRecord | str) -> HkbRecord:
        if isinstance(record, str):
            record = self._behavior[record]

        if record.object_id:
            self._behavior.objects.pop(record.object_id)
            undo_manager.on_delete_object(record)
            return record

        return None

    def array_add(self, record: HkbRecord | str, path: str, item: Any) -> None:
        if isinstance(record, str):
            record = self._behavior[record]

        array: HkbArray = record.get_path_value(path)
        array.append(item)
        undo_manager.on_update_array_item(array, -1, None, item)

    def array_pop(self, record: HkbRecord | str, path: str, index: int) -> Any:
        if isinstance(record, str):
            record = self._behavior[record]

        array: HkbArray = record.get_path_value(path)
        ret = array.pop(index).get_value()
        undo_manager.on_update_array_item(array, index, ret, None)
        return ret

    def free_state_id(self, statemachine: HkbRecord | str) -> int:
        statemachine = get_object(self._behavior, self._behavior, statemachine)
        return get_next_state_id(statemachine)

    def bind_variable(
        self,
        obj: HkbRecord | str,
        path: str,
        variable: Variable | str | int,
    ) -> None:
        obj = get_object(self._behavior, obj)

        if isinstance(variable, Variable):
            variable = variable.index

        return bind_variable(self._behavior, obj, path, variable)

    def make_copy(
        self,
        source: HkbRecord | str,
        *,
        object_id: str = "<new>",
        **overrides
    ) -> HkbRecord:
        source = get_object(source)

        attributes = {k:v.get_value() for k,v in source.get_value().items()}
        attributes.update(**overrides)

        return self.new(
            source.type_name,
            object_id=object_id,
            **attributes
        )

    def new_variable(
        self,
        name: str,
        data_type: VariableType = VariableType.INT32,
        range_min: int = 0,
        range_max: int = 0,
    ) -> Variable:
        idx = self._behavior.create_variable(name, data_type, range_min, range_max)
        undo_manager.on_create_variable(self._behavior, name)
        return Variable(idx, name)

    def get_variable(self, name: str) -> Variable:
        return Variable(self._behavior.find_variable(name), name)

    def new_event(self, event: str) -> Event:
        idx = self._behavior.create_event(event)
        undo_manager.on_create_event(self._behavior, event)
        return Event(idx, event)

    def get_event(self, name: str) -> Event:
        return Event(self._behavior.find_event(name), name)

    def new_animation(self, animation: str) -> Animation:
        idx = self._behavior.create_animation(animation)
        undo_manager.on_create_animation(self._behavior, animation)
        return Animation(
            idx,
            self._behavior.get_animation(idx, full_name=False),
            self._behavior.get_animation(idx, full_name=True),
        )

    def get_animation(self, short_name: str) -> Animation:
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

    # Offer common defaults and highlight required settings for the most common objects

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
