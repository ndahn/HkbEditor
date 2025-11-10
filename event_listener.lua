local socket = require("socket")

local port = 27072
local sock = nil
local original_hkbFireEvent = hkbFireEvent


hkbFireEvent = function(state)
    pcall(send_string(state))
    original_hkbFireEvent(state)
end


function open_socket()
    if sock then
        -- Already open
        return sock
    end
    
    sock = socket.udp()
    return sock
end


function send_string(message)
    if not sock then
        open_socket()
    end
    
    sock:sendto(message, "127.0.0.1", port)
    return true
end


function close_socket()
    if sock then
        sock:close()
        sock = nil
    end
end
