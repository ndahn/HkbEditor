# Ash of War

Creates ClipGenerators that are typically used in ashes of war, e.g. for a regular AOW with follow-ups it will register 040000, 040005, 040010, etc. Entries that already exist will be skipped.

Variations for specific weapon types are handled in HKS. Search for `SwordArtsOneShotCategory` in your [c0000.hks](https://github.com/ividyon/EldenRingHKS/blob/870d3776d33110049fede8f7282d9f25823e11a4/c0000.hks#L2235) for more details. The tables below will provide details on which IDs are used based on the AOW and weapon type.

---

## Regular AOW

| Slot               | Base ID | [Type Variations][#weapon-type-variations] |
| ------------------ | ------- | ------------------------------------------ |
| Start              | 040000  | all                                        |
| Start NoFP         | 040005  | all                                        |
| 1st Follow-Up      | 040010  | 1, 2, 4, 6, 9, 10                          |
| 1st Follow-Up NoFP | 040015  | 1, 2, 4, 6, 9, 10                          |
| 2nd Follow-Up      | 040020  | 1, 2, 4, 9                                 |
| 2nd Follow-Up NoFP | 040025  | 1, 2, 4, 9                                 |

---

## Stance AOW

| Slot                     | Base ID | [Type Variations][#weapon-type-variations] |
| ------------------------ | ------- | ------------------------------------------ |
| Start                    | 40050   | -                                          |
| Loop Idle                | 40051   | -                                          |
| Loop Move                | 40052   | -                                          |
| Loop Stop                | 40053   | -                                          |
| Loop Cancel              | 40054   | -                                          |
| Start NoFP               | 40055   | -                                          |
| Loop Idle NoFP           | 40056   | -                                          |
| Loop Move NoFP           | 40057   | -                                          |
| Loop Stop NoFP           | 40058   | -                                          |
| Attack Light             | 40060   | -                                          |
| Attack Light Cancel      | 40061   | -                                          |
| Attack Light 180         | 40062   | -                                          |
| Attack Light Start       | 40061   | -                                          |
| Attack Light NoFP        | 40065   | -                                          |
| Attack Light Cancel NoFP | 40066   | -                                          |
| Attack Light 180 NoFP    | 40067   | -                                          |
| Attack Light Start NoFP  | 40068   | -                                          |
| Attack Heavy             | 40070   | -                                          |
| Attack Heavy 180         | 40072   | -                                          |
| Attack Heavy Start       | 40073   | -                                          |
| Attack Heavy NoFP        | 40075   | -                                          |
| Attack Heavy 180         | 40077   | -                                          |
| Attack Heavy Start       | 40078   | -                                          |

---

## Charge AOW

| Slot              | Base ID | [Type Variations][#weapon-type-variations] |
| ----------------- | ------- | ------------------------------------------ |
| Start             | 40000   | all                                        |
| Cancel Early      | 40001   | 1, 2, 7, 8, 9                              |
| Cancel Late       | 40002   | -                                          |
| Loop              | 40003   | -                                          |
| Loop End          | 40004   | -                                          |
| Start NoFP        | 40005   | all                                        |
| Cancel Early NoFP | 40006   | 1, 2, 7, 8, 9                              |
| Cancel Late NoFP  | 40007   | -                                          |
| Loop NoFP         | 40008   | -                                          |
| Loop End NoFP     | 40009   | -                                          |

---

## Shield AOW

| Slot          | Base ID | [Type Variations][#weapon-type-variations] |
| ------------- | ------- | ------------------------------------------ |
| Start         | 40040   | 7, 8                                       |
| Cancel        | 40041   | 7, 8                                       |
| Loop          | 40043   | 7, 8                                       |
| Loop End      | 40044   | 7, 8                                       |
| Start NoFP    | 40045   | 7, 8                                       |
| Cancel NoFP   | 40046   | 7, 8                                       |
| Loop NoFP     | 40068   | 7, 8                                       |
| Loop End NoFP | 40049   | 7, 8                                       |

---

## Rolling AOW

| Slot       | Base ID | [Type Variations][#weapon-type-variations] |
| ---------- | ------- | ------------------------------------------ |
| Front      | 40080   | -                                          |
| Back       | 40081   | -                                          |
| Left       | 40082   | -                                          |
| Right      | 40083   | -                                          |
| Sub        | 40084   | -                                          |
| Front NoFP | 40085   | -                                          |
| Back NoFP  | 40086   | -                                          |
| Left NoFP  | 40087   | -                                          |
| Right NoFP | 40088   | -                                          |

---

## Weapon Type Variations

???+ tip

    Simply add the listed offset to the AOW slot ID. For example, the ID for a regular AOW's first follow up with no FP will be 040015. For large weapons it becomes 040215, for small shields it becomes 044815, etc.

???+ warning

    Note that the game is very inconsistent about which AOW slots actually support weapon type variations. The template will register whichever variations are possible. Otherwise you'll have to check if there is a CMSG with the animation ID you're interested in (e.g. `animId=40215` ).

| SwordArtsOneShotCategory | Weapon Type                         | ID Offset |
| -----------------------: | ----------------------------------- | --------: |
|                        1 | Large                               |       200 |
|                        2 | Polearm                             |       300 |
|                        3 | Short Sword/Dagger                  |      2000 |
|                        4 | Twinblade                           |      2400 |
|                        5 | Curved Sword                        |      2800 |
|                        6 | Fist/Martial Arts/Perfume/BeastClaw |      4200 |
|                        7 | Large Shield                        |      4700 |
|                        8 | Small Shield                        |      4800 |
|                        9 | Backhand Sword                      |      5800 |
|                       10 | Dueling Shield                      |      5900 |
