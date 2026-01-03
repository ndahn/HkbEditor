# Evasion

???+ quote

    - Author: Shiki
    - Status: untested

Creates a new rolling/evasion animations for players. 

If you have not added new rolling animations before, your new roll will be on index `4`. Otherwise check the log output. As an alternative, locate the `Rolling_Selector` object to figure out how many other variants already exist - your new roll will be that number +1. 

To enable your new roll you can change the `EvasionWeightIndex` variable inside the `SetWeightIndex` function:

```lua
-- Adjust speffect ID as needed
if env(GetSpEffectID, 123456) == TRUE then 
    SetVariable("EvasionWeightIndex", <index>)  -- your evasion index!
end 
```
