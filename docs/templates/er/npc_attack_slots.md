# NPC Attack Slots

???+ quote

    - Author: FloppyDonuts
    - Status: verified

Creates new NPC attack slots starting at aXXX_YYYYYY, where X is the category and Y equals `anim_id_start + anim_id_step * i` and `i` going from 0 to num_attacks (exclusive). The attacks will be associated with the events `W_AttackYYYY` and `W_EventYYYY` (leading 0s not included).

???+ warning
    
    Usually NPC attacks should be in the range from 3000 to 3100. Attacks outside this range need special changes in the HKS to be useful.

For every generated attack you should add the following functions to your enemy's HKS (usually `c9997.hks`):

```lua
function AttackYYYY_onActivate()
    CallActionState(YYYY)
end

function AttackYYYY_onUpdate()
    if AttackCommonFunction(YYYY, STYLE_DEFAULT, TRUE) == TRUE then
        return
    end
end
```

`c9997.hks` is controlled from the enemies' battle AI scripts, which makes a request to execute a certain action by posting the `YYYY` to the engine. This ID is then retrieved in HKS via `env(GetAIActionType)` and leads to more specific animation management (e.g. attacking, guarding, parrying, etc.) based on the *range* it is in. The ranges are set via a couple of global variables. There are a lot of predefined ranges, but the most important ones for Elden Ring (SotE) are:

```lua
ANIME_ID_ATTACK_BEGIN = 3000
ANIME_ID_ATTACK_END = 3039
ANIME_ID_GUARD_ATTACK_BEGIN = 3100
ANIME_ID_GUARD_ATTACK_END = 3104
ANIME_ID_THROW_ERROR_ATTACK = 3110
ANIME_ID_ART_STANCE_BEGIN = 3200
ANIME_ID_ART_STANCE_END = 3204
```

This means that new attack slots between 3040 and 3100 can simply be enabled by adjusting `ANIME_ID_ATTACK_END`. However, if you are creating new slots outside of this range (e.g. 3300-3400) you have to add some additional code in the relevant `ExecAI<Something>` function. For example, when adding a new range for attack slots you would add something like this in `ExecAIAttack`:

```lua
...
if action_type >= 3300 and action_type <= 3400 then
    ExecAttack(action_type)
    return TRUE
end
...
```

You can of course also add global variables for your range and reference those instead.

???+ note

    Ride attacks use different function patterns, check the HKS for examples.
