# NPC Attack Slots

???+ quote

    - Author: FloppyDonuts
    - Status: verified

Creates new NPC attack slots starting at aXXX_YYYYYY, where X is the category and Y equals `anim_id_start + anim_id_step * i` and `i` going from 0 to num_attacks (exclusive). The attacks will be associated with the events `W_AttackYYYYYY` and `W_EventYYYYYY` (leading 0s not included).

NOTE that NPC attacks should be in the range from 3000 to 3100. Attacks outside this range need special changes in the HKS to be useful.
