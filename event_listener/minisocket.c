#include <lua.h>
#include <lauxlib.h>
#include <string.h>

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
    typedef int socklen_t;
    #define CLOSE_SOCKET closesocket
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #define CLOSE_SOCKET close
#endif

/* Lua 5.1 compatible integer check */
static int luaL_checkint_compat(lua_State *L, int arg) {
    return (int)luaL_checknumber(L, arg);
}

static int l_udp_new(lua_State *L) {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        lua_pushnil(L);
        lua_pushstring(L, "socket creation failed");
        return 2;
    }
    lua_pushinteger(L, sock);
    return 1;
}

static int l_udp_sendto(lua_State *L) {
    int sock = luaL_checkint_compat(L, 1);
    size_t msg_len;
    const char *msg = luaL_checklstring(L, 2, &msg_len);
    const char *ip = luaL_checkstring(L, 3);
    int port = luaL_checkint_compat(L, 4);
    
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((unsigned short)port);
    addr.sin_addr.s_addr = inet_addr(ip);
    
    int result = sendto(sock, msg, (int)msg_len, 0,
                       (struct sockaddr*)&addr, sizeof(addr));
    
    if (result < 0) {
        lua_pushnil(L);
        lua_pushstring(L, "sendto failed");
        return 2;
    }
    
    lua_pushboolean(L, 1);
    lua_pushinteger(L, result);
    return 2;
}

static int l_udp_close(lua_State *L) {
    int sock = luaL_checkint_compat(L, 1);
    CLOSE_SOCKET(sock);
    lua_pushboolean(L, 1);
    return 1;
}

static int l_udp_settimeout(lua_State *L) {
    int sock = luaL_checkint_compat(L, 1);
    int timeout_ms = luaL_checkint_compat(L, 2);
    
#ifdef _WIN32
    DWORD timeout = timeout_ms;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (char*)&timeout, sizeof(timeout));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (char*)&timeout, sizeof(timeout));
#else
    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif
    
    lua_pushboolean(L, 1);
    return 1;
}

static const luaL_Reg funcs[] = {
    {"udp_new", l_udp_new},
    {"udp_sendto", l_udp_sendto},
    {"udp_close", l_udp_close},
    {"udp_settimeout", l_udp_settimeout},
    {NULL, NULL}
};

/* Lua 5.1 module initialization */
LUALIB_API int luaopen_minisocket(lua_State *L) {
#ifdef _WIN32
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif
    
    /* Lua 5.1 style registration */
    luaL_register(L, "minisocket", funcs);
    return 1;
}