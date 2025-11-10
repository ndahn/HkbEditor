-- Load our minisocket library from this script's directory

-- TODO this fails outside c0000.hks for some reason
local script_dir = debug.getinfo(1, "S").source:sub(2):match("(.*/)"):gsub("/", "\\")
-- TODO This will always see the game's directory and ME3 doesn't intercept loadlib
package.cpath = script_dir .. "?.dll;" .. package.cpath
local minisocket = require("minisocket")

-- Change the port if you like
local port = 27072

local sock = nil
local original_hkbFireEvent = hkbFireEvent


hkbFireEvent = function(state)
    pcall(send_string, state)
    original_hkbFireEvent(state)
end


function open_socket()
    if sock then
        -- Already open
        return sock
    end
    
    sock = minisocket.udp_new()
    return sock
end


function close_socket()
    if sock then
        minisocket.udp_close(sock)
        sock = nil
    end
end


function send_string(message)
    if not sock then
        open_socket()
    end
    
    minisocket.udp_sendto(sock, message, "127.0.0.1", port)
    return true
end
