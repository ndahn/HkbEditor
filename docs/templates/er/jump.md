# New Jump Type

???+ quote

    - Author: Raster
    - Status: verified

Creates a new TAE slot for jump animations with support for directional jumps and jump attacks.

If you define an animation for one of the directions it will be the only slot used for this direction. Otherwise the regular slots for this direction are used, taken from the "base_jump". These are in Elden Ring 202020 - 202023 (front, back, left, right). 

???+ tip

    To stay compatible with other jump types your `jump_name` should only be a single letter. Elden Ring uses `N` - neutral, `F` - forward, and `D` - dash.

It is highly recommended to keep jump attacks enabled. If jump attacks are enabled, the new jump behaviors will support all jump attacks already registered for the base jump.

???+ note

    Directional jumps are not available for "Jump_N" (neutral jumps). Use "Jump_F" (walking) or "Jump_D" (running) instead if you want those. The main difference is whether you can change direction after the jump started.


## HKS

After this template has succeeded, add the following code inside the `ExecJump` function, replacing the SpEffect ID and event with values appropriate for your behavior.

```lua
if env(GetSpEffectID, 480098) == TRUE then
    if env(IsAIJumpRequested) == TRUE then
        act(NotifyAIOfJumpState)
    end

    act(SetNpcAIAttackRequestIDAfterBlend, env(GetNpcAIAttackRequestID))
    SetAIActionState()
    ExecEvent("W_MyNewJump")

return TRUE
```

Then add the following code on the global level, renaming the functions to match the `jump_name` you specified.

```lua
function MyNewJump_onActivate()
    act(AIJumpState)
    SetAIActionState()
end

function MyNewJump_onUpdate()
    SetAIActionState()
    -- Global variable to remember which landing/running animation to use. 
    -- Set the one that represents your jump best to 1, all others to 0.
    JUMP_STATE_1 = 0  -- N
    JUMP_STATE_2 = 0  -- F
    JUMP_STATE_3 = 1  -- D

    if GetVariable("JumpAttackForm") == 0 then
        act(LockonFixedAngleCancel)
    end
    
    if JumpCommonFunction(2) == TRUE then
        return
    end
end

function MyNewJump_onDeactivate()
    act(DisallowAdditiveTurning, FALSE)
end
```
