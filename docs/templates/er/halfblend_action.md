# Halfblend Action

???+ quote

    - Author: Managarm
    - Status: confirmed

Creates a new upper halfblend statemachine for running upper body animations while walking.

???+ warning

    The `base_name` is important as it will be part of the generated statemachine, events and (if `function_call` is true) called HKS function. That function will be called `<base_name>_Activate`.

The regular animation slots are all meant for oneshot animations, e.g. firing or reloading a crossbow. You can assign the labels freely, they will be appended to the generated nodes' names. Only slots with an animation *and* name will be generated. 

If you need a looping animation place it in the `loop` slot (for the idle) and `loop_move` for when you're moving. The `motion_blend` attribute decides which movement type to use.

Halfblends are activated in HKS using `ExecEventHalfBlend`, which takes two arguments: a tuple defining the halfblend state, and a value to decide what to do with the rest of the body. The tuple is made up of three values: 

1. the event to fire
2. the state ID of the state containing the halfblend statemachine
3. the initial state ID of the halfblend statemachine

These will depend on your setup, the template will print these on the terminal once it's done. Simply copy and paste them to your `c0000.hks`, then call something like `ExecEventHalfBlend(Event_AttackCrossbowRightStart, ALLBODY)`.

```lua
-- Example
ATTACKCROSSBOWRIGHT_DEF0 = 13
ATTACKCROSSBOWRIGHTSTART_DEF1 = 0
Event_AttackCrossbowRightStart = {"W_AttackCrossbowRightStart", ATTACKCROSSBOWRIGHT_DEF0,ATTACKCROSSBOWRIGHTSTART_DEF1}

-- Then somewhere later
ExecEventHalfBlend(Event_AttackCrossbowRightStart, ALLBODY)
```
