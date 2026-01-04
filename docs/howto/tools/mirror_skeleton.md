# Mirroring Skeletons

HkbEditor also covers some more obscure corner cases. One of them is mirroring skeletons. This is useful when you have an animation and want to flip it left <-> right without editing it. As FromSoft never uses this, most characters are not properly setup for this. 

???+ example

    This process requires a `Skeleton.xml` file. To generate it, either use Havok's `FileConvert.exe --xml {Skeleton.hkx} {Skeleton.xml}`, or use *Havok Content Tools*. For the latter, prune all animation data except for the skeleton, then write to platform as XML. If all of this sounds like arcane sorcery, ask around on [*?ServerName?*](https://discord.gg/J5msG6Es) and someone can probably send you the .xml.

In order to fix a character's mirror definitions, select *Tools -> Mirror Skeleton*. In the new dialog, first load the `Skeleton.xml` file for your character. Then select *Auto Mirror* at the bottom. This will generate a mirrored bone mapping based on the `_L`/`_R` suffixes of the bones. Save the resulting xml to the `Character` folder of your extracted `behbnd.dcx` and convert it back using HKLib. 

To mirror an animation, find the corresponding *hkbClipGenerator* and set the *MIRROR* flag.
