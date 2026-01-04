
# Anatomy of a behavior

## Nodes
Every node in the graph has two things: a unique identifier, e.g. *object1234*, and a type, e.g. *hkbStateMachine*. 

???+ warning

    Note that object IDs are **not** stable - they can and will change as you convert between the binary and xml representations.

The type defines which attributes the object has and what their types are. Every attribute consists of a field name and a value. The fundamental attribute types are:

- Integer (*whole numbers*)
- Float (*decimal numbers*)
- Boolean (*true/false*)
- String (*text*)
- Pointer (*reference to another object*)
- Record (*complex object with attributes*)
- Arrays (*lists of values of one of the above types*)

![](assets/guide/attributes-1.png)

In HkbEditor, pointers are used for creating the graph representation, and each node displays at least its ID and type. Most nodes also have a "name" attribute, which will be shown as well. 

???+ info

    In Havok terms, only these named nodes are proper behavior nodes, but there are very few cases where this matters.

---

## State machines
As hinted earlier, Havok behaviors are essentially graphs of state machines. All state machines have one or more states (of type *hkbStateMachine::StateInfo*), and while most states will branch into a variety of animations, they may also contain additional state machines. In this way, more than one state machine can be active at any time, and there is a single root state machine (typically called *Root*) to which all others are indirectly connected.

In HkbEditor, all state machines are listed on the left in alphabetical order, regardless of where they appear in the hierarchy. This means that if you start from e.g. the "Attack_SM" state machine, it is possible to navigate to the "AttackRight_SM". 

---

## Events
States are activated via *Events*. If you have edited one of the games' HKS scripts before you will probably be familiar with lines similar to `ExecEvent("W_SwordArtsOneShot")`. This tells the behavior to activate all states (and state machines) that listen to the *W_SwordArtsOneShot* event. The associations between events and states are stored in the state machine's *wildcardTransitions*.

![](assets/guide/wildcard-transitions-1.png)

You will notice that the *eventId* and *toStateId* attributes are using numbers rather than names. This is fairly common in behaviors. State IDs can be freely defined and are set in the state's *stateId* attribute. Events are stored in a separate list though, and as they are referenced by their index, changing their order or inserting new events in between would screw up everything that comes after. To view, edit and add events you can use the *Edit -> Events* dialog. To select a new event for an event attribute, either enter its index or use the *arrow button* next to the attribute to select an existing event.

???+ danger

    Transitions that reference non-existing states or statemachines containing duplicate state IDs will cause the game to crash.

---

## Variables
Most attributes can also be bound to a variable. In this case they will no longer have a fixed value, but can be controlled via HKS. If you have seen something like `SetVariable("ItemWeaponType", 1)` you are actually changing the value of some behavior attribute. This is quite powerful, and is used in Elden Ring for example to select different a different roll type based on the current weight. These can also be set from the animation by using TAE 605 (*SetTimeActEditorHavokVariable*). As with events, variables are referenced by their index and can be edited via *Edit -> Variables*. 

![](assets/guide/variable-bindings-1.png)

In order to bind a variable, right click a bindable attribute and select *Bind Variable*. Note that you can only bind attributes of nodes that have a *variableBindingSet* attribute (which is the object where the binding is stored). This is true for all proper behavior nodes.

---

## Animations
Probably what most people will care about, and so of course I put it towards the end :) 

In order to play back an animation a behavior needs 3 things:

- A state to activate
- An event to activate the state
- And a *hkbClipGenerator* object

The first two should be clear by now, and the clip generator will be shortly. It's a relatively simple object that crucially defines which animation to play, as well as various playback parameters like playback speed, what to do once the animation finishes (e.g. nothing or loop), etc.

![](assets/guide/clipgen-1.png)

Each animation must be registered in a global list (similar to how events and variables are handled). You can edit this list from the *Edit -> Animations* dialog.

However, there are usually a couple more objects between a clip generator and its state, and this is where the magic comes in.

---

## CMSG & Manual Selectors
Let's say you are creating a new ash of war for Elden Ring. The animation is ready, everything is setup, you just need to execute it somehow. You open a state machine and... hm. Do you really want to add an entire new state to it? You would have to create a new event, too. And you couldn't reuse all the HKS code for checking sufficient stamina, player input, weapon type, FP cost,... Not a good option.

Looking at Elden Ring's *SwordArts_SM* (which is the general state machine for ashes of war), you notice that it actually has a fairly complex structure. First there are different states for different variations like shield, charged, stances, etc., some of which lead to other state machines like *SwordArtsStance_SM*. But even the most basic state - *SwordArtsOneShot* (040000 and related) - contains a *ManualSelectorGenerator* object, which again has more manual selectors and... what's going on?

![](assets/guide/manual-selectors-1.png)

A *ManualSelectorGenerator* will activate one of its children (the generators) based on its *selectedGeneratorIndex* attribute. This attribute is usually bound to a variable, in the case of the first selector *IsEnoughArtPointsR2*. This makes it easy to execute either the 040000 or 040005 animation depending on whether your character currently has enough FP! The subsequent manual selectors use the *SwordArtsOneShotCategory* variable to play back different animations based on the weapon type you're holding. In HKS the latter looks similar to this this (simplified for the sake of this guide):

```lua
local arts_cat = GetSwordArtsCategory()
local arts_idx = 0

if arts_cat == WEAPON_CATEGORY_LARGE_KATANA then
    arts_idx = 1

elseif arts_cat == WEAPON_CATEGORY_POLEARM then
    arts_idx = 2

elseif arts_cat == WEAPON_CATEGORY_SHORT_SWORD then
    arts_idx = 3

-- and so on...
end

SetVariable("SwordArtsOneShotCategory", arts_idx)
ExecEventAllBody("W_SwordArtsOneShot")
```

You could of course now create a separate generator for every different ash of war, weapon type, and attack and use variables to meticulously decide which animation to play back. But this system will fail in many unintuitive ways - for example if you insert a new animation in between the already existing generators. 

The better way to do this is to use what's called a *CustomManualSelectorGenerator*, or CMSG for short. This object will select a single clip generator from its children based on e.g. the currently equipped ash of war. Other options include selected magic, idle category, weapon type, etc. CMSGs are also responsible for calling HKS functions based on their name. For example, a CMSG called *SwordArtsOneshotComboEnd_CMSG* will also call the following HKS functions (if they exist and *enableScript* is set to true):

- SwordArtsOneshotComboEnd_onActivate
- SwordArtsOneshotComboEnd_onUpdate
- SwordArtsOneshotComboEnd_onDeativate

![](assets/guide/cmsg-1.png)

This means that in order to use a new ash of war you simply need to add a *hkbClipGenerator* to the appropriate CMSG. In HkbEditor this can be done by selecting *Workflows -> Register Clip*, whereas *Create CMSG* will create a new state, CMSG and clip generator.

???+ info

    This is essentially what *ERClipGenerator* does: it looks for already known animation IDs and creates clip generator objects in the corresponding CMSGs.

---

## Blend Layers & Other Objects
I currently don't know enough about these to explain (or use) them. Your best bet is to look at existing structures and ask around on [*?ServerName?*](https://discord.gg/J5msG6Es). 
