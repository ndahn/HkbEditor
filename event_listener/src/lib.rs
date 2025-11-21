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
use std::ffi::CStr;
use std::net::UdpSocket;
use std::path::PathBuf;
use std::time::Duration;
use windows::core::PCWSTR;
use windows::Win32::System::LibraryLoader::{GetModuleFileNameW, GetModuleHandleW};

use eldenring_util::system::wait_for_system_init;
use shared::program::Program;

// RVAs for 1.16.1
const HKBFIREEVENTHKS_RVA: u32 = 0x145a960;
const LUA_GETSTRING_RVA: u32 = 0x14e26c0;
const LUA_GETHKBSELF_RVA: u32 = 0x14522e0;
const LUA_GETHAVOKSTRUCT_RVA: u32 = 0x1451760;

static_detour! {
    static HkbFireEventHook: unsafe extern "C" fn(usize) -> usize;
}

#[derive(Deserialize, Debug)]
struct Config {
    port: u16,
    chr: String,
    print: bool,
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
        let remote = format!("127.0.0.1:{}", config.port);

        let _ = sock.send_to("[hkb_event_listener] I'm alive!".as_bytes(), &remote);

        println!(
            "[hkb_event_listener] will publish events to 127.0.0.1:{}",
            config.port
        );

        unsafe {
            let program = Program::current();

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

            if let Err(e) =
                HkbFireEventHook.initialize(hkb_fire_event_fn, move |lua_state: usize| {
                    // TODO find a way to get the current character ID
                    let hkbself_ptr = lua_gethkbself_fn(lua_state);
                    let behavior_context = get_hkbcontext_fn(lua_state, hkbself_ptr);

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
                                && (config.chr.is_empty()
                                    || character_id.unwrap().starts_with(config.chr.as_str()))
                            {
                                let lua_str_ptr = lua_getstring_fn(lua_state, 1, 0);
                                let event_str =
                                    CStr::from_ptr(lua_str_ptr as *const i8).to_str().unwrap();
                                let data_str = format!("{}:{}", character_id.unwrap(), event_str);

                                if config.print {
                                    println!("{}", data_str);
                                }

                                let _ = sock.send_to(data_str.as_bytes(), &remote);
                            }
                        }
                    }

                    return HkbFireEventHook.call(lua_state);
                })
            {
                eprintln!("[hkb_event_listener] failed to initialise detour: {e}");
                return;
            }
            if let Err(e) = HkbFireEventHook.enable() {
                eprintln!("[hkb_event_listener] failed to enable detour: {e}");
                return;
            }
        }
    });
    true
}
