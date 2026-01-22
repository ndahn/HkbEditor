# Game Event (Player)

???+ quote

    - Author: VIVID
    - Status: confirmed

Creates multipe NPC game events that can be triggered from HKS, EMEVD, ESD, objects, etc. This is always a full animation, half blends are not possible. Event animations are often used for boss phase transitions. Once registered it can be used like any other animation.

???+ note 

    The event IDs will also correspond to the animation IDs.

???+ warning

    NPC events are usually limited to 20000..20059 and 30000..30029. If you need additional slots you'll have to edit the `ANIME_ID_EVENT_BEGIN` and `ANIME_ID_EVENT_END` variables in the NPC's HKS. 

???+ danger

    Don't forget to run `File -> Update name ID files` to add new entries to `action/eventnameid.txt`!

---
