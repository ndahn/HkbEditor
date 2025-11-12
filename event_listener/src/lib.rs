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

const PATTERN: [Option<u8>; 14] = [
    Some(0x48),
    Some(0x8b),
    Some(0x47),
    Some(0x10),
    Some(0x48),
    Some(0x89),
    Some(0x42),
    Some(0x10),
    Some(0xff),
    Some(0x43),
    Some(0x10),
    Some(0xff),
    Some(0x43),
    Some(0x14),
];

const FUNC_START: usize = 0x6D;

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

impl Config {
    fn chr_id(&self) -> u32 {
        self.chr.trim_start_matches('c').parse().unwrap_or(0)
    }
}

static CONFIG: OnceCell<Config> = OnceCell::new();

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
                .unwrap_or_else(|_| String::from(r#"{"port": 27072, "chr": "c0000"}"#));

            serde_json::from_str(&config_str).unwrap_or(Config {
                port: 27072,
                chr: "c0000".to_string(),
            })
        };

        let _ = CONFIG.set(config);

        // Perform the pattern scan. If the function cannot be found
        // simply bail out: the game version is likely unsupported.
        let Some(addr) = find_event_function() else {
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
                .initialize(target_fn, |hkb_character: *mut c_void, event: *const u16| hook_play_animation(hkb_character, event))
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
                CONFIG.get().unwrap().port
            );
        }
    });
    true
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

/// Detour handler for `hkbFireEvent`. This function is invoked each time
/// the game fires a behaviour event. It forwards the event name via UDP
/// and then calls into the original function so that the game continues
/// operating normally.
unsafe extern "C" fn hook_play_animation(hkb_character: *mut c_void, event: *const u16) {
    let config = CONFIG.get().expect("Config was not initialized");
    let chr_ins = get_chr_ins_from_hkb(hkb_character);

    if chr_ins.character_id == config.chr_id() {
        // Read event ID
        let event_struct = event as *const u32;
        let event_id = ptr::read(event_struct);
        
        let _ = send_event_via_udp(event_id.to_string().as_str());
    }
    
    // Call the original function
    HkbFireEventHook.call(hkb_character, event);
}

/// Get the ChrIns instance from an hkbCharacter pointer
unsafe fn get_chr_ins_from_hkb(hkb_character: *mut c_void) -> &'static mut ChrIns {
    // TODO crashes
    let hkb_ptr = hkb_character as *const u8;
    let chr_ins_ptr_ptr = hkb_ptr.add(0x28) as *const *mut ChrIns;
    let chr_ins_ptr = ptr::read(chr_ins_ptr_ptr);
    &mut *chr_ins_ptr
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
    // TODO use config.port instead
    let remote = "127.0.0.1:27072";
    sock.send_to(event.as_bytes(), remote)?;
    Ok(())
}

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
