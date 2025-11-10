# From CE Hexinton


## Current animation
4 bytes @ 0x7FF429E84640
250030000 -> a250_030000

=> (character) <ChrIns>
=> module_container <ChrInsModuleContainer>
=> time_act <CSChrTimeActModule>
=> hkv_anim <CSChrTimeActModuleAnim> ? 
=> anim_id


## Play animation
```lua
local aob = AOBScanModuleUnique(process,"74 ?? 48 85 d2 74 ?? 48 8d 4c 24 50")
local W_Event_addr = aob - 0xD

function PlayAnimation(str)
    if type(str) ~= "string" then
        error("Input needs to be string type",2)
    end
    -- WorldChrMan -> PlayerIns -> ChrModules ->
    -- CSChrBehaviorModule -> ? -> hkbCharacter
    local ptr = getAddressSafe("[[[[[WorldChrMan]+1E508]+190]+28]+10]+30")
    if ptr == nil then
        error("'hkbCharacter' not found",2)
    end
    local mem_addr = allocateMemory(64, getAddress(process))
    if writeString(mem_addr,str,true) then
        if executeCodeEx(0, 100, W_Event_addr, ptr, mem_addr) == 0xFFFFFFFF then
            print("Failed to play: ", str)
        end
    end
    deAlloc(mem_addr)
end
```

In eldenring-rs this becomes:
=> (character) <ChrIns>
=> module_container <ChrInsModuleContainer>
=> behavior <CSChrBehaviorModule>
=> unk10 <?>
=> unk30 <hkbCharacter>

The function is then located at the AOB - 0xD.
This is NOT hkbFireEvent, but seems to be something low-level that the game doesn't use.


## Watch memory location
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;

/// Watch a 4-byte memory location and call a callback when it changes.
/// This spawns a background thread that polls the memory location.
pub fn watch_memory_u32(
    address: usize,
    callback: impl Fn(u32, u32) + Send + 'static,
    poll_interval: Duration,
) -> std::thread::JoinHandle<()> {
    std::thread::spawn(move || {
        let mut last_value = unsafe { ptr::read_volatile(address as *const u32) };
        
        loop {
            std::thread::sleep(poll_interval);
            
            let current_value = unsafe { ptr::read_volatile(address as *const u32) };
            
            if current_value != last_value {
                callback(last_value, current_value);
                last_value = current_value;
            }
        }
    })
}

/// Example usage: watch a specific address and send changes over UDP
pub fn example_watch_memory() {
    let address_to_watch = 0x12345678; // Replace with actual address
    
    let _handle = watch_memory_u32(
        address_to_watch,
        |old_val, new_val| {
            eprintln!("[memory_watch] value changed: 0x{:X} -> 0x{:X}", old_val, new_val);
            
            // Send notification over UDP
            let message = format!("memory_change:{:X}:{:X}", old_val, new_val);
            let _ = UdpSocket::bind("127.0.0.1:0")
                .and_then(|sock| sock.send_to(message.as_bytes(), "127.0.0.1:12345"));
        },
        Duration::from_millis(16), // Check every ~60 FPS
    );
    
    // The handle can be stored if you need to join/cancel later
}
