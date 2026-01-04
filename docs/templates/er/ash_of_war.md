# Ash of War

???+ quote

    - Author: Managarm
    - Status: confirmed

Creates ClipGenerators that are typically used in ashes of war, e.g. for a regular AOW with follow-ups it will register 040000, 040005, 040010, etc. Entries that already exist will be skipped.

[Weapon type variations](#weapon-type-variations) are handled in HKS. Search for `SwordArtsOneShotCategory` in your [c0000.hks](https://github.com/ividyon/EldenRingHKS/blob/870d3776d33110049fede8f7282d9f25823e11a4/c0000.hks#L2235) for more details. The tables below will provide details on which IDs are used based on the AOW slot.

---

## Regular

| Slot               | Base ID | [Type Variations](#weapon-type-variations) |
| ------------------ | ------- | ------------------------------------------ |
| Start              | 040000  | all                                        |
| Start NoFP         | 040005  | all                                        |
| 1st Follow-Up      | 040010  | 1, 2, 4, 6, 9, 10                          |
| 1st Follow-Up NoFP | 040015  | 1, 2, 4, 6, 9, 10                          |
| 2nd Follow-Up      | 040020  | 1, 2, 4, 9                                 |
| 2nd Follow-Up NoFP | 040025  | 1, 2, 4, 9                                 |

---

## Stance

| Slot                     | Base ID | [Type Variations](#weapon-type-variations) |
| ------------------------ | ------- | ------------------------------------------ |
| Start                    | 040050  | -                                          |
| Loop Idle                | 040051  | -                                          |
| Loop Move                | 040052  | -                                          |
| Loop Stop                | 040053  | -                                          |
| Loop Cancel              | 040054  | -                                          |
| Start NoFP               | 040055  | -                                          |
| Loop Idle NoFP           | 040056  | -                                          |
| Loop Move NoFP           | 040057  | -                                          |
| Loop Stop NoFP           | 040058  | -                                          |
| Attack Light             | 040060  | -                                          |
| Attack Light Cancel      | 040061  | -                                          |
| Attack Light 180         | 040062  | -                                          |
| Attack Light Start       | 040061  | -                                          |
| Attack Light NoFP        | 040065  | -                                          |
| Attack Light Cancel NoFP | 040066  | -                                          |
| Attack Light 180 NoFP    | 040067  | -                                          |
| Attack Light Start NoFP  | 040068  | -                                          |
| Attack Heavy             | 040070  | -                                          |
| Attack Heavy 180         | 040072  | -                                          |
| Attack Heavy Start       | 040073  | -                                          |
| Attack Heavy NoFP        | 040075  | -                                          |
| Attack Heavy 180         | 040077  | -                                          |
| Attack Heavy Start       | 040078  | -                                          |

---

## Charge

| Slot              | Base ID | [Type Variations](#weapon-type-variations) |
| ----------------- | ------- | ------------------------------------------ |
| Start             | 040000  | all                                        |
| Cancel Early      | 040001  | 1, 2, 7, 8, 9                              |
| Cancel Late       | 040002  | -                                          |
| Loop              | 040003  | -                                          |
| Loop End          | 040004  | -                                          |
| Start NoFP        | 040005  | all                                        |
| Cancel Early NoFP | 040006  | 1, 2, 7, 8, 9                              |
| Cancel Late NoFP  | 040007  | -                                          |
| Loop NoFP         | 040008  | -                                          |
| Loop End NoFP     | 040009  | -                                          |

---

## Shield

| Slot          | Base ID | [Type Variations](#weapon-type-variations) |
| ------------- | ------- | ------------------------------------------ |
| Start         | 040040  | 7, 8                                       |
| Cancel        | 040041  | 7, 8                                       |
| Loop          | 040043  | 7, 8                                       |
| Loop End      | 040044  | 7, 8                                       |
| Start NoFP    | 040045  | 7, 8                                       |
| Cancel NoFP   | 040046  | 7, 8                                       |
| Loop NoFP     | 040068  | 7, 8                                       |
| Loop End NoFP | 040049  | 7, 8                                       |

---

## Rolling

| Slot       | Base ID | [Type Variations](#weapon-type-variations) |
| ---------- | ------- | ------------------------------------------ |
| Front      | 040080  | -                                          |
| Back       | 040081  | -                                          |
| Left       | 040082  | -                                          |
| Right      | 040083  | -                                          |
| Sub        | 040084  | -                                          |
| Front NoFP | 040085  | -                                          |
| Back NoFP  | 040086  | -                                          |
| Left NoFP  | 040087  | -                                          |
| Right NoFP | 040088  | -                                          |

---

## Weapon Type Variations

???+ tip

    Simply add the listed offset to the AOW slot ID. For example, the ID for a regular AOW's first follow up with no FP will be 040015. For large weapons it becomes 040215, for small shields it becomes 044815, etc.

???+ warning

    Note that Elden Ring is very inconsistent about which AOW slots actually support weapon type variations. The template will register whichever variations are possible. Otherwise you'll have to check if there is a CMSG with the animation ID you're interested in (e.g. `animId=40215` ).

| SwordArtsOneShotCategory | Weapon Type                         | ID Offset |
| -----------------------: | ----------------------------------- | --------- |
|                        1 | Large                               | 200       |
|                        2 | Polearm                             | 300       |
|                        3 | Short Sword/Dagger                  | 2000      |
|                        4 | Twinblade                           | 2400      |
|                        5 | Curved Sword                        | 2800      |
|                        6 | Fist/Martial Arts/Perfume/BeastClaw | 4200      |
|                        7 | Large Shield                        | 4700      |
|                        8 | Small Shield                        | 4800      |
|                        9 | Backhand Sword                      | 5800      |
|                       10 | Dueling Shield                      | 5900      |
