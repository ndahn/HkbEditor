# Throw Attack (Attacker)

???+ quote

    - Author: FloppyDonuts
    - Status: confident

Creates a new throw attack behavior (i.e. grabbing an enemy).

Throws and grabs are controlled by the ThrowParam table of the `regulation.bin`. After adding a new grab behavior, create new rows as needed and set the `atkAnimId` field to the animation ID of your `grab_anim` (ignoring the aXXX part, i.e. a000_004170 becomes 4170).
