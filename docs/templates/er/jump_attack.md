# Jump Attack

Creates an entirely new jump attack type, e.g. left-handed jump attacks. 

In Elden Ring, jump attacks are layered animations in the `NewJump Statemachine`, where a jump animation serves as a basis and applies root motion, while an optional attack animation can be applied on top without altering the trajectory. This is controlled by a hierarchy of `ManualSelectorGenerators` and enabling additional animation layers.

It is important to understand that jumps go through several phases: the initial jump defines the type of jump (neutral - `N`, forward - `F`, dash - `D`). It then transitions into the jump loop, then a falling loop (optional), and finally a landing animation (or death fall). Since these are represented by separate states, each phase has a similar but duplicate structure of jump attack nodes. Since the states are separate, it is not possible to continue playing an animation across them - each state has its own ClipGenerators. To make it appear as if the attack continues, the ClipGenerators have their `startTime` attribute bound to a variable. When one phase ends the next phase's attack animation starts where the animation was when the previous phase ended.

???+ info

    Jump loop is somewhat special since it usually uses an attack loop animation - basically holding the weapon in a certain way while falling.

The behavior can be activated by setting the `JumpAttackForm` and `JumpAttack_HandCondition` variables in the following places:

- `ExecJump`
- `ExecJumpLoopDirect`
- `ExecFallAttack`
- `JumpCommonFunction`
- `Jump_Loop_onUpdate`
- `ExecRideOff`

Depending on your base jump type you should also modify the following functions:

- `JumpAttack_Start_Falling_onUpdate`
- `JumpAttack_Start_Falling_F_onUpdate`
- `JumpAttack_Start_Falling_D_onUpdate`

Lastly, if you're creating a new jump magic type you need to update these functions:

- `ExecJumpMagic`
- `ExecFallMagic`


???+ quote

    - Author: Managarm
    - Status: needs testing
