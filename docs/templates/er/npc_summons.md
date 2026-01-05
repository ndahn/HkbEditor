# NPC Summons

???+ quote

    - Author: FloppyDonuts
    - Status: confirmed

Makes an NPC summonable if it isn't already. This will create the BuddyGenerate and BuddyDisappear states in the Master_SM, which are activated by firing W_BuddyGenerate and W_BuddyDisappear (as well as W_Event1830 and W_Event1840).

To add the new summon to the game you'll have to setup the following params in Smithbox:

- BuddyParam
- SpEffectParam
- GoodsParam
- NpcParam
- NpcThinkParam

I have not done this myself yet, so I can't give any details. Look at existing summons and try to replicate what FromSoft did!
