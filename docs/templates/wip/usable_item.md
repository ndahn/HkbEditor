# Usable Item

???+ quote

    - Author: FloppyDonuts
    - Status: wip

Creates a new usable item that can be used as a oneshot, for weapon enchants, or both. The item will be used like every other regular item. For weapon buff items, the `W_ItemWeaponEnchant` (or `W_ItemWeaponEnchant_Upper`) event is responsible.

Oneshot items will only use the `normal_use_anim`. Weapon buff items should also specify the `backhandblade_anim` and `duelingshield_ainm`. If not specified, the `normal_use_anim` will be used instead.

