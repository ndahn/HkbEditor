There are a couple of nodes in the behavior that will call HKS functions while they are active. The `Update` function will be called every frame without exception from the behavior root. 

Most states will also call a function based on their name. When a state activates it calls its `onActivate` function, and when it deactivates its `onDeactivate` function. While active it will call its `onUpdate` every frame. 

For example, while the character is in its *Idle* state, the `Idle_onUpdate` function will be called. This then calls `IdleCommonFunction`, which in turn tries to call a bunch of `ExecX` functions, like `ExecAttack`, `ExecEvasion`, and so on until one of them succeeds. These functions then decide what to do based on button inputs, character equipment, animation state, etc. 

`ExecX` functions will usually end with a call to `ExecEvent`, `ExecEventAllBody`, or similar (if they succeed). Events are strings that usually start with `W_`, for example `W_AttackRightLight1`. The events then go to the behavior where they will cause transitions to new states (usually using [wildcard transitions](../anatomy#events)). 

In our example, `W_AttackRightLight1` will be fired, causing `Idle` to call its `onDeactivate` function. Meanwhile, the `AttackRightLight1` state will call its `AttackRightLight1_onActivate` function, and then `AttackRightLight1_onUpdate` during the following frames (which leads to `AttackCommonFunction` and so on).

Take into account the TAE events from the animations (which are run by `hkbClipGenerator` nodes) and you have the full game loop.
