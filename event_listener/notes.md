## Current animation
- From CE Hexinton
- 4 bytes @ 0x7FF429E84640
- 250030000 -> a250_030000

=> (character) <ChrIns>
=> module_container <ChrInsModuleContainer>
=> time_act <CSChrTimeActModule>
=> hkv_anim <CSChrTimeActModuleAnim> ? 
=> anim_id


# PlayAnimationBehaviorName
=> Used by cheat engine
First argument is the hkbCharacter, second the animation event.
Unfortunately, this is not actually used by the game.

74 ?? 48 85 d2 74 ?? 48 8d 4c 24 50  -->  -0xD

To get the hkbCharacter:
=> (character) <ChrIns>
=> module_container <ChrInsModuleContainer>
=> behavior <CSChrBehaviorModule>
=> unk10 <?>
=> unk30 <hkbCharacter>


# fireHkbEvent_C
=> Called for all animation events. 
First parameter is the hkbCharacter, second one the event ID, which corresponds with the eventnameids.txt file

48 8b 47 10 48 89 42 10 ff 43 10 ff 43 14  -->  -0x6D

There is probably a function to convert the ID back to a string. 
However...


# FUN_14145a960 (fireHkbEvent_HKS)
=> This is the function lua calls as hkbFireEvent!
Takes a single argument, the hks_lua_State. 

- Uses hkbInternal::hksi_luaL_checklstring to get the string argument
- Calls GetHkbSelf
- Does something weird to get the hkbCharacter
  - GetVariable has a much cleaner approach
  - getHkbSelf -> GetHkbContext -> GetHkbCharacter -> +0x40
- Calls FireHkbEvent_C


# hkbCharacter
=> Fields:
24 0x18  nearbyCharacters
 40 0x28  userData
 48 0x30  currentLod
 50 0x32  numTracksInLod
 56 0x38  generatorOutput
 64 0x40  name
 72 0x48  nameFromFile
 80 0x50  ragdollDriver
 88 0x58  ragdollInterface
 96 0x60  characterControllerDriver
104 0x68  footIkDriver
112 0x70  handIkDriver
120 0x78  bodyIkDriver
128 0x80  dockingDriver
136 0x88  aiDriver
144 0x90  setup
152 0x98  behaviorGraph
160 0xa0  projectData
168 0xa8  animationBindingSet
176 0xb0  spatialQueryInterface
184 0xb8  world
192 0xc0  boneAttachments
208 0xd0  eventQueue
216 0xd8  characterLuaState
224 0xe0  assetManager
232 0xe8  capabilities
236 0xec  effectiveCapabilities
240 0xf0  globalSymbolLinker
248 0xf8  characterSymbolLinker
256 0x100 userDatasMap
288 0x120 deltaTime
292 0x124 useCharactorDeltaTime

=> The name field at 0x40 contains the character's name

*=> behaviorGraph has a getActiveNodes function, returning a NodeList!*


# AOB pattern matching
```rust
/// Walk the current module's memory looking for the `hkbFireEvent` signature.
/// On success returns the absolute address of the beginning of the function.
/// On failure returns `None`. The search is limited to the size reported in
/// the PE header to avoid scanning uninitialised pages.
fn find_event_function() -> Option<usize> {
    // TODO allow different characters than c0000

    // Acquire the base address of the current module. Passing a null
    // parameter to `GetModuleHandleA` returns a handle to the file used to
    // create the calling process.
    let base_handle = unsafe { GetModuleHandleA(PCSTR(ptr::null())).ok()? };
    let module_base = base_handle.0 as usize;
    if module_base == 0 {
        return None;
    }
    unsafe {
        // Read the DOS and NT headers to obtain the image size. These
        // structures live at fixed offsets relative to the module base.
        let dos_header = &*(module_base as *const IMAGE_DOS_HEADER);
        let nt_header =
            &*((module_base + dos_header.e_lfanew as usize) as *const IMAGE_NT_HEADERS64);
        let image_size = nt_header.OptionalHeader.SizeOfImage as usize;
        let base_ptr = module_base as *const u8;

        eprintln!(
            "[hkb_fire_event_hook] scanning module at 0x{:X}, size: 0x{:X}",
            module_base, image_size
        );

        // Iterate over the image looking for the signature. Because of
        // wildcards the inner loop breaks early on mismatches.
        let pat_len = PATTERN.len();
        for offset in 0..(image_size.saturating_sub(pat_len)) {
            let mut matched = true;
            for (i, pat_byte) in PATTERN.iter().enumerate() {
                if let Some(b) = pat_byte {
                    if *base_ptr.add(offset + i) != *b {
                        matched = false;
                        break;
                    }
                }
            }
            if matched {
                // Adjust by -0xD to obtain the start of the function.
                let addr = base_ptr.add(offset).wrapping_sub(FUNC_START) as usize;
                return Some(addr);
            }
        }
        None
    }
}
```
