![](doc/icon.png)

This program allows you to edit Havok behavior graphs which are used in several FromSoft games like *Nightreign*, *Elden Ring*, and *Sekiro - Shadows Die Twice*. 

There is now a shiny new documentation page over at [](https://ndahn.github.io/HkbEditor/) :tada:!

---

# What the hell is this?
Behaviors are one of the more obscure subsystems in these games, controling which animations to play or add on top of each other, as well as how to transition between them. This is modeled in the form of state machines where each state controls (part of) an animation. States can transition to new states either automatically, or by triggering events from HKS, the script files handling player input and game state.

![image](https://github.com/user-attachments/assets/c9a1fe5a-63c1-44a9-a770-5608277b4c12)

---

# In case something breaks
If you find any bugs or missing features, preferably create an issue here on github. Alternatively, ping me *@managarm* over on [?ServerName?](https://discord.gg/wzMynmW).
