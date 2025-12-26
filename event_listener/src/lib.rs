//! Elden Ring hkbFireEvent hook
//!
//! This crate produces a DLL which hooks the `hkbFireEvent` method of
//! `hkbCharacter`. When the game raises a behaviour event (for example to
//! trigger an animation) the mod intercepts the call, extracts the event name
//! and forwards it over UDP before delegating to the original function. The
//! address of the function is discovered at runtime via a simple pattern scan
//! (see [`PATTERN`]). The hook is installed on DLL attach and remains
//! active for the duration of the game session. When compiled and placed
//! alongside other Elden Ring mods (e.g. via `libraryloader`) this code will
//! automatically intercept events without any additional input from the user.

#![allow(non_snake_case)]

use pelite::pe64::Pe;
use retour::static_detour;
use serde::Deserialize;
use std::ffi::c_void;
use std::ffi::{CStr, CString};
use std::net::UdpSocket;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;
use windows::core::PCWSTR;
use windows::Win32::System::LibraryLoader::{GetModuleFileNameW, GetModuleHandleW};

use eldenring_util::system::wait_for_system_init;
use shared::program::Program;

// RVAs for 1.16.1
const PUSHHKSGLOBALS1_RVA: u32 = 0x145ce30;
const HKS_ADDNAMEDCCLOSURE_RVA: u32 = 0x145d9d0;
const HKBFIREEVENTHKS_RVA: u32 = 0x145a960;
const LUA_GETSTRING_RVA: u32 = 0x14e26c0;
const LUA_GETHKBSELF_RVA: u32 = 0x14522e0;
const LUA_GETHAVOKSTRUCT_RVA: u32 = 0x1451760;

static_detour! {
    static PushHksGlobals1Hook: unsafe extern "C" fn(usize) -> usize;
    static HkbFireEventHook: unsafe extern "C" fn(usize) -> usize;
}

#[derive(Deserialize, Debug, Clone)]
struct Config {
    port: u16,
    chr: String,
    print: bool,
}

/// Collection of game function pointers resolved from RVAs
#[derive(Clone, Copy)]
struct GameFunctions {
    pushhksglobals1_fn: unsafe extern "C" fn(usize) -> usize,
    hks_addnamedcclosure_fn: unsafe extern "C" fn(usize, usize, usize) -> usize,
    hkb_fire_event_fn: unsafe extern "C" fn(usize) -> usize,
    lua_getstring_fn: unsafe extern "C" fn(usize, i32, usize) -> *const i8,
    lua_gethkbself_fn: unsafe extern "C" fn(usize) -> usize,
    get_hkbcontext_fn: unsafe extern "C" fn(usize, usize) -> usize,
}

impl GameFunctions {
    /// Resolve all game function addresses from RVAs
    unsafe fn resolve(program: &Program) -> Self {
        let va = program.rva_to_va(PUSHHKSGLOBALS1_RVA).unwrap();
        let pushhksglobals1_fn = 
            std::mem::transmute::<u64, unsafe extern "C" fn(usize) -> usize>(va);

        let va = program.rva_to_va(HKS_ADDNAMEDCCLOSURE_RVA).unwrap();
        let hks_addnamedcclosure_fn = 
            std::mem::transmute::<u64, unsafe extern "C" fn(usize, usize, usize) -> usize>(va);

        let va = program.rva_to_va(HKBFIREEVENTHKS_RVA).unwrap();
        let hkb_fire_event_fn =
            std::mem::transmute::<u64, unsafe extern "C" fn(usize) -> usize>(va);

        let va = program.rva_to_va(LUA_GETSTRING_RVA).unwrap();
        let lua_getstring_fn = std::mem::transmute::<
            u64,
            unsafe extern "C" fn(usize, i32, usize) -> *const i8,
        >(va);

        let va = program.rva_to_va(LUA_GETHKBSELF_RVA).unwrap();
        let lua_gethkbself_fn =
            std::mem::transmute::<u64, unsafe extern "C" fn(usize) -> usize>(va);

        let va = program.rva_to_va(LUA_GETHAVOKSTRUCT_RVA).unwrap();
        let get_hkbcontext_fn =
            std::mem::transmute::<u64, unsafe extern "C" fn(usize, usize) -> usize>(va);

        Self {
            pushhksglobals1_fn,
            hks_addnamedcclosure_fn,
            hkb_fire_event_fn,
            lua_getstring_fn,
            lua_gethkbself_fn,
            get_hkbcontext_fn,
        }
    }
}

/// Shared context for all hook functions
struct HookContext {
    sock: UdpSocket,
    config: Config,
    game_fns: GameFunctions,
}

static HOOK_CONTEXT: Mutex<Option<HookContext>> = Mutex::new(None);

/// Lua C function that receives a string from Lua and sends it over UDP
unsafe extern "C" fn send_string_lua(lua_state: usize) -> i32 {
    let context_guard = HOOK_CONTEXT.lock().unwrap();
    if let Some(context) = context_guard.as_ref() {
        // Get the string argument from Lua stack at index 1
        let lua_str_ptr = (context.game_fns.lua_getstring_fn)(lua_state, 1, 0);
        
        if !lua_str_ptr.is_null() {
            if let Ok(message) = CStr::from_ptr(lua_str_ptr).to_str() {
                let remote = format!("127.0.0.1:{}", context.config.port);
                let text = format!("debug:{}", message);

                if context.config.print {
                    println!("{}", text);
                }

                let _ = context.sock.send_to(text.as_bytes(), &remote);
            }
        }
    }
    
    // Return 0 to indicate no return values pushed to Lua stack
    0
}

/// Detour function for PushHksGlobals1 - registers custom Lua functions
unsafe fn pushhksglobals1_detour(lua_state: usize) -> usize {
    {
        let context_guard = HOOK_CONTEXT.lock().unwrap();
        if let Some(context) = context_guard.as_ref() {
            // Register our custom function in Lua's global namespace
            // Function name must be null-terminated C string
            let function_name = CString::new("DebugSend").unwrap();
            let _ = (context.game_fns.hks_addnamedcclosure_fn)(
                lua_state,
                function_name.as_ptr() as usize,
                send_string_lua as usize
            );
        }
    }
    
    // Call the original function to continue normal initialization
    PushHksGlobals1Hook.call(lua_state)
}

/// Detour function for HkbFireEvent - intercepts behavior events and forwards them over UDP
unsafe fn hkbfireevent_detour(lua_state: usize) -> usize {
    // Lock inside limited scope, unlock before calling the original function.
    // Some game events like item pickups may lead to additional calls to hkbfireevent 
    // before this function returns, which would lead to a deadlock!
    {
        let context_guard = HOOK_CONTEXT.lock().unwrap();
        if let Some(context) = context_guard.as_ref() {
            let hkbself_ptr = (context.game_fns.lua_gethkbself_fn)(lua_state);
            let behavior_context = (context.game_fns.get_hkbcontext_fn)(lua_state, hkbself_ptr);

            // FUN_141451730 just dereferences behavior_context
            let hkbcharacter_ptr = *(behavior_context as *const usize);

            if hkbcharacter_ptr != 0 {
                // Name is an attribute of hkbCharacter at 0x40
                let string_and_flag = *((hkbcharacter_ptr + 0x40) as *const usize);

                // Make sure the pointer is in userspace
                if string_and_flag > 0x10000000000 {
                    // The stored string is a hkStringPtr, which stores a flag in the
                    // first byte. Usually 0, but just in case.
                    let actual_string_ptr = (string_and_flag & !1) as *const i8;
                    let character_id = CStr::from_ptr(actual_string_ptr).to_str();

                    // Enemies are usually named something like c4080_1234, where 1234
                    // is probably their model variation
                    if character_id.is_ok()
                        && (context.config.chr.is_empty()
                            || character_id.unwrap().starts_with(context.config.chr.as_str()))
                    {
                        let lua_str_ptr = (context.game_fns.lua_getstring_fn)(lua_state, 1, 0);
                        let event_str =
                            CStr::from_ptr(lua_str_ptr as *const i8).to_str().unwrap();
                        let data_str = format!("{}:{}", character_id.unwrap(), event_str);

                        if context.config.print {
                            println!("{}", data_str);
                        }

                        let remote = format!("127.0.0.1:{}", context.config.port);
                        let _ = context.sock.send_to(data_str.as_bytes(), &remote);
                    }
                }
            }
        }
    } // lock released

    HkbFireEventHook.call(lua_state)
}

fn get_dll_dir_path() -> Option<PathBuf> {
    let dll_name = "hkb_event_listener.dll\0";
    let wide_dll_name: Vec<u16> = dll_name.encode_utf16().collect();
    let module = unsafe { GetModuleHandleW(PCWSTR::from_raw(wide_dll_name.as_ptr())) }.ok()?;
    let mut buffer = [0u16; 260];
    let length = unsafe { GetModuleFileNameW(module, &mut buffer) };
    if length == 0 {
        return None;
    }

    let path_str = String::from_utf16_lossy(&buffer[..length as usize]);
    let path = PathBuf::from(path_str);
    Some(path.parent()?.to_path_buf())
}

/// Entry point executed by the Windows loader. The hook is installed
/// asynchronously when the DLL is attached to the process. Returning
/// `true` indicates success to the loader.
#[no_mangle]
pub unsafe extern "system" fn DllMain(
    _hinstance: *mut c_void,
    reason: u32,
    _reserved: *mut c_void,
) -> bool {
    // DLL_PROCESS_ATTACH == 1 on Windows
    if reason != 1 {
        return true;
    }
    // Spawn a detached thread so that heavy initialisation does not block
    // the loader. Within this thread we wait for the game to finish
    // initialising, perform the pattern scan and install the detour.
    std::thread::spawn(|| {
        // Wait for Elden Ring's systems to initialise. Without this the
        // program module might not yet be mapped and `Program::current()`
        // could panic.
        if let Err(e) = wait_for_system_init(&Program::current(), Duration::MAX) {
            eprintln!("[hkb_event_listener] failed to wait for system init: {e}");
            return;
        }

        let config: Config = {
            let config_path = get_dll_dir_path()
                .map(|p| p.join("hkb_event_listener.yaml"))
                .unwrap_or_else(|| PathBuf::from("hkb_event_listener.yaml"));

            let config_str = std::fs::read_to_string(config_path)
                .unwrap_or_else(|_| String::from(r#"{"port": 27072, "chr": "c0000", "print": false}"#));

            serde_yaml::from_str(&config_str).unwrap_or(Config {
                port: 27072,
                chr: "c0000".to_string(),
                print: false,
            })
        };

        let sock = UdpSocket::bind("127.0.0.1:0").expect("Failed to open socket");

        let _ = sock.send_to(
            "[hkb_event_listener] I'm alive!".as_bytes(),
            &format!("127.0.0.1:{}", config.port)
        );

        println!(
            "[hkb_event_listener] will publish events to 127.0.0.1:{}",
            config.port
        );

        unsafe {
            let program = Program::current();

            // Resolve all game function addresses from RVAs
            let game_fns = GameFunctions::resolve(&program);

            // Clone the socket for the hook context
            let sock_clone = sock.try_clone().expect("Failed to clone socket");
            
            // Initialize global hook context shared by all detours
            *HOOK_CONTEXT.lock().unwrap() = Some(HookContext {
                sock: sock_clone,
                config,
                game_fns,
            });

            // Install our hook for PushHksGlobals1
            if let Err(e) = 
                PushHksGlobals1Hook.initialize(
                    game_fns.pushhksglobals1_fn,
                    |lua_state| pushhksglobals1_detour(lua_state)
                )
            {
                eprintln!("[hkb_event_listener] failed to register PushHksGlobals1 detour: {e}");
                return;
            }
            if let Err(e) = PushHksGlobals1Hook.enable() {
                eprintln!("[hkb_event_listener] failed to enable PushHksGlobals1 detour: {e}");
                return;
            }

            // Install our hook for HkbFireEvent
            if let Err(e) =
                HkbFireEventHook.initialize(
                    game_fns.hkb_fire_event_fn,
                    |lua_state| hkbfireevent_detour(lua_state)
                )
            {
                eprintln!("[hkb_event_listener] failed to initialise HkbFireEvent detour: {e}");
                return;
            }
            if let Err(e) = HkbFireEventHook.enable() {
                eprintln!("[hkb_event_listener] failed to enable HkbFireEvent detour: {e}");
                return;
            }
        }
    });
    true
}
