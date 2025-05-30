# HkbEditor
I'll write a proper *ReadMe* later. For now this is the absolute basics you need to know:
- only loads behavior XML files
- is largely untested
- removes XML comments on save (to be fixed)

Most things like graph nodes, attributes, etc. have useful menus on right click. You can move around the graph with middle mouse button + drag (potentially weird on laptops?). Zoom, reveal all, etc. somewhat works, but don't be surprised if something looks messed up. Reopening the statemachine will usually fix this.

![image](https://github.com/user-attachments/assets/c9a1fe5a-63c1-44a9-a770-5608277b4c12)

## Features included (and probably working):
- navigate state machine graphs
- edit any attribute
- add and remove items from arrays, including arrays of records
- mappings for the most common enums I'm aware of
- pin objects for future reference
- load bone names from skeletons and show them in BoneWeightArrays
- edit variables, events and animation names
- create and edit variable bindings (fields will show "@variable")
- search for objects, advanced search using Lucene syntax
- generate CMSGs, including ClipGenerator, StateInfo and TransitionInfo

Many things are there, but most received only basic testing and some of the dialogs are rather rudimentary. Things will improve over time. If a menu item is greyed out that usually means I have not implemented it yet. 

## Upcoming Features
- ClipGenerator registration (similar to ERClipGenerator)
- visualize StateInfo graph

I have very little experience with actually doing anything with behaviors. Please let me know if there are features you are (desperately) missing!

**IMPORTANT:** for the likely case that you find bugs, either @ping me on discord or open a github issue. 
