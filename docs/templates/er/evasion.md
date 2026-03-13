# Evasion

???+ quote

    - Author: Shiki
    - Status: confirmed

Creates a new rolling/evasion animations for players.

Note that in ER/NR the rolling and backstep animations are tied together. There are three ways to fix this for new evasions: 

1. reuse existing backsteps,
2. register new backsteps manually to keep them in sync, or 
3. rebind one of the selectors' attributes to a new variable and adjust your HKS (specifically the `SetWeightIndex` function).

ER also comes with an unused "superlight" backstep, which will interfere with any new evasion types. This template will remove it so the rolling and backstep selectors are in sync.

???+ info

    When setting a manual selector's selected generator index to a value outside its range, Havok will use the last generator instead.

If you have not added new rolling animations before, your new roll will be on index `4`. Otherwise check the log output. As an alternative, locate the `Rolling_Selector` object to figure out how many other variants already exist - your new roll will be that number +1. 

To enable your new roll you can change the `EvasionWeightIndex` variable inside the `SetWeightIndex` function:

```lua
-- Adjust speffect ID as needed
if env(GetSpEffectID, 123456) == TRUE then 
    SetVariable("EvasionWeightIndex", <index>)  -- your evasion index!
end 
```
