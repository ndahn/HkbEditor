# Weapon Moveset

???+ quote

    - Author: Managarm
    - Status: confirmed

Creates ClipGenerators that are typically used in weapon movesets, e.g. for right-handed attacks it will register 030000, 030010, etc. Entries that already exist will be skipped.

Unless otherwise noted, the events for the attack slots listed below are the name of the slot prefixed with a `W_` (e.g. `W_AttackRightLight1`).

???+ note
    
    Special and warrior attacks will only be registered if right and/or both are checked.

???+ note
    
    Jump attacks will only be registered if right, both, and/or dual are checked.


---

## Right Hand

| Slot | ID |
| ---- | -- |
| AttackRightLight1 | 30000 |
| AttackRightLight2 | 30010 |
| AttackRightLight3 | 30020 |
| AttackRightLight4 | 30030 |
| AttackRightLight5 | 30040 |
| AttackRightLight6 | 30050 |
| AttackRightLightDash | 30200 |
| AttackRightHeavyDash | 30210 |
| AttackRightLightStep | 30300 |
| AttackRightBackstep | 30400 |
| AttackRightHeavy1Start | 30500 |
| AttackRightHeavy1SubStart | 30501 |
| AttackRightHeavy1End | 30505 |
| AttackRightHeavy2Start | 30510 |
| AttackRightHeavy2End | 30515 |
| AttackRightLightCounter* | 30700 |

???+ note

    *) AttackRightLightCounter and AttackRightHeavyCounter use the same animation ID.

---

## Two-Handed (both)

| Slot | ID |
| ---- | -- |
| AttackBothLight1 | 32000 |
| AttackBothLight2 | 32010 |
| AttackBothLight3 | 32020 |
| AttackBothLight4 | 32030 |
| AttackBothLight5 | 32040 |
| AttackBothLight6 | 32050 |
| AttackBothLightDash | 32200 |
| AttackBothHeavyDash | 32210 |
| AttackBothLightStep | 32300 |
| AttackBothBackstep | 32400 |
| AttackBothHeavy1Start | 32500 |
| AttackBothHeavy1SubStart | 32501 |
| AttackBothHeavy1End | 32505 |
| AttackBothHeavy2Start | 32510 |
| AttackBothHeavy2End | 32515 |
| AttackBothLightCounter* | 32700 |

???+ note

    *) AttackBothLightCounter and AttackBothHeavyCounter use the same animation ID.

---

## Dual

| Slot | ID |
| ---- | -- |
| AttackDualRight1 | 34000 |
| AttackDualRight2 | 34010 |
| AttackDualRight3 | 34020 |
| AttackDualRight4 | 34030 |
| AttackDualDash | 34200 |
| AttackDualRolling | 34300 |
| AttackDualBackStep | 34400 |

---

## Left

| Slot | ID |
| ---- | -- |
| AttackLeftHeavy1* | 35000 |
| AttackLeftHeavy2 | 35010 |
| AttackLeftHeavy3 | 35020 |
| AttackLeftHeavy4 | 35030 |
| AttackLeftHeavy5 | 35040 |
| AttackLeftHeavy6 | 35050 |

???+ note

    *) AttackLeftHeavy1 is equal to AttackLeftLight1, probably a remnant from early development. The other attacks have no *light* event associated.

---

## Backstab

| Slot | ID |
| ---- | -- |
| ThrowBackStap | 31719 |

???+ note

    Weapons can override any throw defined in the `Throw_SM -> ThrowAtk`. To generate new throws, see [Throw Attack (Attacker)]. 31700 is the throw fallback, e.g. when the grab failed.

---

## Special

### Special Right

| Slot | ID |
| ---- | -- |
| AttackRightHeavySpecial1Start | 30600 |
| AttackRightHeavySpecial1SubStart | 30601 |
| AttackRightHeavySpecial1End | 30605 |
| AttackRightHeavySpecial2Start | 30610 |
| AttackRightHeavySpecial2End | 30615 |


### Special Both

| Slot | ID |
| ---- | -- |
| AttackBothHeavySpecial1Start | 32600 |
| AttackBothHeavySpecial1SubStart | 32601 |
| AttackBothHeavySpecial1End | 32605 |
| AttackBothHeavySpecial2Start | 32610 |
| AttackBothHeavySpecial2End | 32615 |

---

## Warrior

### Warrior Right

| Slot | ID |
| ---- | -- |
| AttackRightHeavyWarrior1Start | 30620 |
| AttackRightHeavyWarrior1SubStart | 30621 |
| AttackRightHeavyWarrior1End | 30625 |
| AttackRightHeavyWarrior2Start | 30630 |
| AttackRightHeavyWarrior2End | 30635 |


### Warrior Both

| Slot | ID |
| ---- | -- |
| AttackBothHeavyWarrior1Start | 32620 |
| AttackBothHeavyWarrior1SubStart | 32621 |
| AttackBothHeavyWarrior1End | 32625 |
| AttackBothHeavyWarrior2Start | 32630 |
| AttackBothHeavyWarrior2End | 32635 |

---

## Jump

### Jump Right

???+ warning

    Jump attacks are layered animations and are not activated the usual way. The "slots" given here are often not unique and only serve to illustrate what they are used for. See the [Jump Attack template](jump_attack.md) for further details.

| Slot | ID |
| ---- | -- |
| JumpAttack_N_Normal_Right | 31030 |
| JumpAttack_F_Normal_Right | 31040 |
| JumpAttack_D_Normal_Right | 31050 |
| Jump_Loop_Attack_Normal_Right | 31060 |
| Jump_LandAttack_Normal_Right | 31070 |
| JumpAttack_N_Hard_Right | 31230 |
| JumpAttack_F_Hard_Right | 31240 |
| JumpAttack_D_Hard_Right | 31250 |
| Jump_Loop_Attack_Hard_Right | 31260 |
| Jump_LandAttack_Hard_Right | 31270 |

### Jump Both

| Slot | ID |
| ---- | -- |
| JumpAttack_N_Normal_Both | 33030 |
| JumpAttack_F_Normal_Both | 33040 |
| JumpAttack_D_Normal_Both | 33050 |
| Jump_Loop_Attack_Normal_Both | 33060 |
| Jump_LandAttack_Normal_Both | 33070 |
| JumpAttack_N_Hard_Both | 33230 |
| JumpAttack_F_Hard_Both | 33240 |
| JumpAttack_D_Hard_Both | 33250 |
| Jump_Loop_Attack_Hard_Both | 33260 |
| Jump_LandAttack_Hard_Both | 33270 |

### Jump Dual

| Slot | ID |
| ---- | -- |
| JumpAttack_N_Normal_Dual | 34530 |
| JumpAttack_F_Normal_Dual | 34540 |
| JumpAttack_D_Normal_Dual | 34550 |
| Jump_Loop_Attack_Normal_Dual | 34560 |
| Jump_LandAttack_Normal_Dual | 34570 |

---

## Ride

| Slot | ID |
| ---- | -- |
| RideAttack_R_Top | 38000 |
| RideAttack_R_Top02 | 38010 |
| RideAttack_R_Top03 | 38020 |
| RideAttack_R_Hard1_Start | 38100 |
| RideAttack_R_Hard1_End | 38110 |
| RideAttack_R_Hard2_Start | 38200 |
| RideAttack_R_Hard1_End_Jump | 38300 |
| RideAttack_L_Top | 39000 |
| RideAttack_L_Top02 | 39010 |
| RideAttack_L_Top03 | 39020 |
| RideAttack_L_Hard1_Start | 39100 |
| RideAttack_L_Hard1_End | 39110 |
| RideAttack_L_Hard2_Start | 39200 |
| RideAttack_L_Hard1_End_Jump | 39300 |

???+ note

    I have no clue how jump attacks are handled :) Additional research is required if you want to use these.
