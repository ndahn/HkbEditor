There are a couple of nodes in the behavior that will call HKS functions while they are active. The `Update` function will be called every frame without exception from the behavior root. 

Most states will also call a function based on their name. When a state activates it calls its `onActivate` function, and when it deactivates its `onDeactivate` function. While active it will call its `onUpdate` every frame. 

For example, while the character is in its *Idle* state, the `Idle_onUpdate` function will be called. This then calls `IdleCommonFunction`, which in turn tries to call a bunch of `Exec` functions, like `ExecAttack`, until one of them succeeds. `ExecAttack` would check for button inputs and, if a button was pressed, check the equipped weapon types and so on to decide what to do. 

These `Exec` functions will usually end with a call to `ExecEvent`, `ExecEventAllBody`, or similar (if they succeed). The event functions take a string, for example `W_AttackRightLight1`, which goes to the behavior where it will cause a transition to a new state. In our case, `Idle` will call its `onDeactivate` function on the next frame. Meanwhile, `AttackRightLight1` will call its `AttackRightLight1_onActivate` function, and then `AttackRightLight1_onUpdate` during the following frames (which leads AttackCommonFunction and so on).

Take into account the TAE events from the animations (which are run by `hkbClipGenerator` nodes) and you have the full game loop.
