# Throw Attack (Victim)

???+ quote

    - Author: FloppyDonuts
    - Status: verified

Creates a new grab victim behavior (i.e. being grabbed by an enemy).

This template will create either 3 or 5 animations depending on the `can_escape` setting:

- `grab_anim + 0`: grab animation
- `grab_anim + 1`: animation used when the character dies during the grab
- `grab_anim + 2`: animation looped after the death animation
- `grab_anim + 3`: escape animation, triggered by W_ThrowEscape in HKS
- `grab_anim + 4`: hold animation, used when the escape fails and usually the same as +0

Throws and grabs are controlled by the ThrowParam table of the regulation.bin. After adding a new grab behavior, create new rows as needed and set the `defAnimId` field to the animation ID of your `grab_anim` (ignoring the aXXX part, i.e. a000_070970 becomes 70970).
