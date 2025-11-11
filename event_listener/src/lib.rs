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

use std::ffi::c_void;
use std::net::UdpSocket;
use std::path::PathBuf;
use std::ptr;
use std::slice;
use std::str::FromStr;
use std::time::Duration;

use once_cell::sync::OnceCell;
use retour::static_detour;
use serde::Deserialize;
use windows::core::{PCSTR, PCWSTR};
use windows::Win32::System::LibraryLoader::{GetModuleFileNameW, GetModuleHandleW};
use windows::Win32::System::Diagnostics::Debug::IMAGE_NT_HEADERS64;
use windows::Win32::System::LibraryLoader::GetModuleHandleA;
use windows::Win32::System::SystemServices::IMAGE_DOS_HEADER;

use eldenring::cs::ChrIns;
use eldenring_util::system::wait_for_system_init;
use shared::program::Program;

/// Signature used to locate the beginning of `hkbFireEvent` within the
/// executable. The bytes come from observing the game binary in Cheat
/// Engine: `74 ?? 48 85 d2 74 ?? 48 8d 4c 24 50`. Wildcards (`None`) match
/// any byte. Once the pattern is found the actual start of the function
/// resides 0xD bytes before the match.
const PATTERN: [Option<u8>; 12] = [
    Some(0x74),
    None,
    Some(0x48),
    Some(0x85),
    Some(0xD2),
    Some(0x74),
    None,
    Some(0x48),
    Some(0x8D),
    Some(0x4C),
    Some(0x24),
    Some(0x50),
];

/// Once initialised this holds the absolute virtual address of the
/// `hkbFireEvent` function. It is discovered via pattern scanning on
/// module load. Other helper functions (e.g. to manually fire an event)
/// can retrieve the value from here.
static HKB_FIRE_EVENT_ADDR: OnceCell<usize> = OnceCell::new();

// Define a static detour for the target function. The calling convention
// specified here must match the original function: on 64‑bit Windows all
// calling conventions share the same ABI so `extern "C"` is sufficient.
static_detour! {
    static HkbFireEventHook: unsafe extern "C" fn(*mut c_void, *const u16);
}

#[derive(Deserialize, Debug)]
struct Config {
    port: u16,
    chr: String,
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

        let _ = send_event_via_udp("[hkb_event_listener] I'm alive!");

        let config: Config = {
            let config_path = get_dll_dir_path()
                .map(|p| p.join("hkb_event_listener.json"))
                .unwrap_or_else(|| PathBuf::from("hkb_event_listener.json"));

            let config_str = std::fs::read_to_string(config_path)
                .unwrap_or_else(|_| String::from(r#"{"port": 27072}"#));
            serde_json::from_str(&config_str).unwrap_or(Config {
                port: 27072,
                chr: String::from_str("c0000").unwrap(),
            })
        };

        // Perform the pattern scan. If the function cannot be found
        // simply bail out: the game version is likely unsupported.
        let Some(addr) = find_hkb_fire_event(config.chr) else {
            eprintln!("[hkb_event_listener] hkbFireEvent pattern not found");
            return;
        };
        println!("[hkb_fire_event_hook] found hkbFireEvent at 0x{:X}", addr);

        // Store the function pointer for later. Note: `OnceCell::set` will
        // silently fail if the cell is already initialised; this helps
        // prevent accidental re‑initialisation.
        let _ = HKB_FIRE_EVENT_ADDR.set(addr);

        // Prepare the detour. We transmute the raw address into a typed
        // function pointer matching the signature defined in the detour.
        let target_fn: unsafe extern "C" fn(*mut c_void, *const u16) =
            unsafe { std::mem::transmute(addr) };

        unsafe {
            // Initialise and enable the detour. Errors are ignored for brevity
            // but could be logged or bubbled up in a real mod.
            if let Err(e) = HkbFireEventHook
                .initialize(target_fn, |this_, event| hook_hkb_fire_event(this_, event))
            {
                eprintln!("[hkb_event_listener] failed to initialise detour: {e}");
                return;
            }
            if let Err(e) = HkbFireEventHook.enable() {
                eprintln!("[hkb_event_listener] failed to enable detour: {e}");
                return;
            }

            println!(
                "[hkb_event_listener] will publish events to 127.0.0.1:{}",
                config.port
            );
        }
    });
    true
}

/// Detour handler for `hkbFireEvent`. This function is invoked each time
/// the game fires a behaviour event. It forwards the event name via UDP
/// and then calls into the original function so that the game continues
/// operating normally.
unsafe fn hook_hkb_fire_event(this_: *mut c_void, event: *const u16) {
    // Extract the event name from the wide string pointer. Safety:
    // `event` is assumed to be a valid, null‑terminated UTF‑16 string.
    if let Some(event_str) = wide_c_str_to_string(event) {
        // Attempt to send the event over UDP. Any network errors are
        // silently ignored as we don't want to disrupt gameplay.
        println!("[hkb_event_listener] event: {event_str}");
        let _ = send_event_via_udp(&event_str);
    }
    // Invoke the original function. This uses the detour's `call`
    // method which always forwards to the unhooked implementation.
    HkbFireEventHook.call(this_, event);
}

/// Convert a pointer to a null‑terminated UTF‑16 string into a Rust [`String`].
/// Returns `None` if the pointer is null. See [`slice::from_raw_parts`] for
/// safety details.
unsafe fn wide_c_str_to_string(ptr: *const u16) -> Option<String> {
    if ptr.is_null() {
        return None;
    }
    // Compute the length by walking until a 0 terminator is encountered.
    let mut len = 0usize;
    loop {
        if *ptr.add(len) == 0 {
            break;
        }
        len += 1;
    }
    let slice = slice::from_raw_parts(ptr, len);
    Some(String::from_utf16_lossy(slice))
}

/// Send the provided event name to a UDP listener. By default the mod
/// broadcasts to localhost on port `12345`, but this can be adjusted as
/// required. A fresh socket is bound for each message which avoids the
/// overhead of maintaining a persistent connection and simplifies error
/// handling. Should the socket fail to bind or send, the error is
/// returned to the caller.
fn send_event_via_udp(event: &str) -> std::io::Result<()> {
    // Bind to an OS‑assigned port on localhost. Using port 0 allows
    // the operating system to choose an available port for us.
    let sock = UdpSocket::bind("127.0.0.1:0")?;
    // The receiving port. You can change this to integrate with your
    // visualiser or accessibility tool.
    let remote = "127.0.0.1:27072";
    sock.send_to(event.as_bytes(), remote)?;
    Ok(())
}

/// Walk the current module's memory looking for the `hkbFireEvent` signature.
/// On success returns the absolute address of the beginning of the function.
/// On failure returns `None`. The search is limited to the size reported in
/// the PE header to avoid scanning uninitialised pages.
fn find_hkb_fire_event(chr: String) -> Option<usize> {
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
                let addr = base_ptr.add(offset).wrapping_sub(0xD) as usize;
                return Some(addr);
            }
        }
        None
    }
}

/// Retrieve the `hkbCharacter` pointer from a [`ChrIns`] instance. The
/// character's behavioural module contains an internal pointer at offset
/// `unk10` which itself holds a pointer at offset `0x30` to the Havok
/// behaviour character instance. The returned pointer can be passed to
/// `hkbFireEvent` to trigger events manually.
///
/// # Safety
///
/// This function performs raw pointer arithmetic on memory owned by the
/// game. It is the caller's responsibility to ensure that the provided
/// [`ChrIns`] is valid and that the game is not concurrently freeing the
/// underlying structures.
pub unsafe fn get_hkb_character(chr_ins: &ChrIns) -> Option<*mut c_void> {
    // Navigate through the module container into the behaviour module.
    let container = chr_ins.module_container.as_ref();
    let behavior = container.behavior.as_ref();
    // The behaviour module's `unk10` field stores a pointer to an
    // unspecified structure. We access it via raw pointer arithmetic
    // since the field is private. At offset 0x8 lies unk10, and within
    // that structure at offset 0x30 lies the pointer to `hkbCharacter`.
    let behavior_ptr = behavior as *const _ as *const u8;
    let unk10_ptr = behavior_ptr.add(0x8) as *const usize;
    let unk10 = ptr::read(unk10_ptr) as *const u8;
    if unk10.is_null() {
        return None;
    }
    // Read the pointer located at unk10 + 0x30. Cast the result back to
    // a mutable `c_void` pointer for consumption by `hkbFireEvent`.
    let hkb_ptr_ptr = unk10.add(0x30) as *const *mut c_void;
    let hkb_ptr: *mut c_void = ptr::read(hkb_ptr_ptr);
    if hkb_ptr.is_null() {
        None
    } else {
        Some(hkb_ptr)
    }
}

/// Fire a behaviour event manually on the supplied [`ChrIns`]. This is
/// analogous to the `PlayAnimation` function in the Cheat Engine example.
/// If the `hkbFireEvent` address has not yet been discovered, or the
/// character pointer cannot be resolved, the function quietly returns.
pub fn play_behavior_event(chr_ins: &mut ChrIns, event: &str) {
    // Only proceed if the function has been located. Attempting to
    // transmute a null address would result in undefined behaviour.
    let Some(addr) = HKB_FIRE_EVENT_ADDR.get().copied() else {
        return;
    };
    // Resolve the target pointer
    let hkb_character = unsafe { get_hkb_character(chr_ins) };
    let Some(hkb_ptr) = hkb_character else {
        return;
    };
    // Convert the Rust string into a UTF‑16 buffer with a null terminator.
    let mut wide: Vec<u16> = event.encode_utf16().collect();
    wide.push(0);
    // Cast the discovered address into a callable function pointer with the
    // correct signature. Calling a function through a transmuted pointer
    // is unsafe because the compiler cannot verify the ABI at compile time.
    let fire_event: unsafe extern "C" fn(*mut c_void, *const u16) =
        unsafe { std::mem::transmute(addr) };
    unsafe { fire_event(hkb_ptr, wide.as_ptr()) };
}
