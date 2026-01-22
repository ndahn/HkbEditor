# Game Event (Player)

???+ quote

    - Author: FloppyDonuts
    - Status: hopeful

Create a player game event that can be triggered from HKS, EMEVD, ESD, objects, etc. This is always a full animation, half blends are not possible. A good example for a game event is touching a site of grace. Event animations are typically placed in `a000`. 

To use this game event you need to add the following functions to your `c0000.hks`. The event to activate it will be called `W_EventXXXXX`.

???+ tip

    Remember to replace any mention of XXXXX with your event ID!

```lua
function EventXXXXX_onActivate()
    ResetEventState()
end

function EventXXXXX_onUpdate()
    act(SetIsEventActionPossible, TRUE)
    if EventCommonFunction() == TRUE then
        act(SetIsEventActionPossible, FALSE)
        return
    end
end

function EventXXXXX_onDeactivate()
    act(SetIsEventActionPossible, FALSE)
end
```

???+ danger

    Don't forget to run `File -> Update name ID files` to add new entries to `action/eventnameid.txt`!

---
