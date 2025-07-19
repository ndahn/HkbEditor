# HkbEditor
This program allows you to edit Havok behavior graphs which are used in several FromSoft games like Nightreign, Elden Ring, and Sekiro - Shadows Die Twice. 

*If you have absolutely no idea about behaviors yet, check the [Souls Modding Wiki](https://www.soulsmodding.com/doku.php?id=tutorial:main#animations_and_behaviors)!*

Behaviors are one of the most complex subsystems in these games, controling which animations to play and add on top of each other, as well as how to transition between them. This is modeled in the form of state machines where each state controls (part of) an animation. States can transition to new states either automatically (e.g. by defining events like `<state1>_to_<state2>`), or by triggering events from HKS, the script files handling player input and game state.

![image](https://github.com/user-attachments/assets/c9a1fe5a-63c1-44a9-a770-5608277b4c12)

# How to use
In order to open a behavior you first need to unpack your game using [UXM](https://github.com/Nordgaren/UXM-Selective-Unpack). You want the `chr` folder, which contains animations and behaviors. Next, using [WitchyBND](https://github.com/ividyon/WitchyBND), unpack the `.behbnd.dcx` file of the character behavior you want to edit. This will create a folder with two subfolders and a few files. The behavior this tool is made for is under `Behaviors/cXXXX.hkx`, where *XXXX* is the character's ID. After you decompile it into an XML using [HKLib](https://github.com/The12thAvenger/HKLib) you can open it.

Once loaded, you can expand one of the state machines and move around the graph with middle mouse button + drag (could be weird on some laptops?). Zoom in and out using your mouse wheel. Most things like graph nodes, attributes, etc. have useful menus on right click providing additional actions.

When editing behaviors you should typically rely on making small incremental changes. The most common use cases - registering clips and creating CMSGs - can be found in the *workflows* menu. To create new hierarchies you would typically start by creating a new target for a pointer (e.g. a StateInfo's generator, or a new entry for a CMSG's generators). 

If you have something more complex in mind, definitely have a look at the [templates](https://github.com/ndahn/HkbEditor/blob/main/templates/example.py). There are several examples of varying complexity, and the API is both quite powerful AND the best documented part of the program right now.

This program is still in its early stages. 
___Save frequently and to multiple versions!___

# Features:
- navigate state machine graphs
- edit any attribute
- add and remove items from arrays, including arrays of records
- mappings for most common enums and flags
- pin objects for future reference
- edit variables, events and animation names
- create and edit variable bindings (fields will show "@variable")
- search for objects by name, id and/or their attributes
- generate state machine states (StateInfo + CMSG + ClipGenerator)
- register clips in existing CMSGs
- create arbitrary objects
- write and use templates to cover complex modifications like creating new blend layers
- load bone names from skeletons and show them in BoneWeightArrays
- generate bone mirror maps so clips with the MIRROR flag work properly
- rudimentary visualization of state machine graphs

# Caveats
- **Undo** works for simple stuff like changing an attribute, but may fail for more complex actions like running templates. Save frequently to multiple versions!
- Only loads behavior XML files
- Removes XML comments on save (will restore this at some point)

# In case something breaks
If you find any bugs or missing features, preferably create an issue here on github. Alternatively, ping me *@managarm* over on [?ServerName?](https://discord.gg/wzMynmW).
