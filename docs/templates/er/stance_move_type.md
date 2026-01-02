# Stance Move Type

Creates a new behavior for moving while in a stance. Imagine the difference between moving in unsheathe vs. a bear wanting to hug you.

Once this template succeeds the log output will tell you the index of your new stance move type. This index should be used in hks to activate the move type while an speffect is active. Find the function `SetMoveType` and add a new condition to it as below:

```lua
-- Replace with your speffect ID!
elseif env(GetSpEffectID, 123456) == TRUE then
    SetVariable("MoveType", ConvergeValue(1, hkbGetVariable("MoveType"), 5, 5))
    SetVariable("StanceMoveType", <index>)  -- your index goes here!
...
```


???+ quote

    - Author: Managarm
    - Status: hopeful