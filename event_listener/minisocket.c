/*
TODO 
Must be placed in the game folder. As ER doesn't provide a lua51.dll, we can't link against
it and instead have to make stubs for everything, hoping that it will be provided at runtime.
Even then this library crashes the game upon loading.
*/

#include <lua.h>
#include <lauxlib.h>
#include <string.h>
#ifdef _WIN32
    #include <windows.h>
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

/* Function pointer types */
typedef double (*lua_tonumber_t)(lua_State *L, int idx);
typedef const char* (*lua_tolstring_t)(lua_State *L, int idx, size_t *len);
typedef int (*lua_type_t)(lua_State *L, int idx);
typedef void (*lua_pushinteger_t)(lua_State *L, lua_Integer n);
typedef void (*lua_pushboolean_t)(lua_State *L, int b);
typedef void (*lua_pushstring_t)(lua_State *L, const char *s);
typedef void (*lua_pushnil_t)(lua_State *L);
typedef void (*lua_createtable_t)(lua_State *L, int narr, int nrec);
typedef void (*lua_setfield_t)(lua_State *L, int idx, const char *k);
typedef void (*lua_pushcclosure_t)(lua_State *L, lua_CFunction fn, int n);
typedef int (*luaL_argerror_t)(lua_State *L, int arg, const char *extramsg);

/* Global function pointers */
static lua_tonumber_t my_lua_tonumber = NULL;
static lua_tolstring_t my_lua_tolstring = NULL;
static lua_type_t my_lua_type = NULL;
static lua_pushinteger_t my_lua_pushinteger = NULL;
static lua_pushboolean_t my_lua_pushboolean = NULL;
static lua_pushstring_t my_lua_pushstring = NULL;
static lua_pushnil_t my_lua_pushnil = NULL;
static lua_createtable_t my_lua_createtable = NULL;
static lua_setfield_t my_lua_setfield = NULL;
static lua_pushcclosure_t my_lua_pushcclosure = NULL;
static luaL_argerror_t my_luaL_argerror = NULL;

/* Initialize function pointers by getting them from the calling process */
static int init_lua_functions(lua_State *L) {
    #ifdef _WIN32
    HMODULE hExe = GetModuleHandle(NULL);  /* Get the EXE handle */
    
    my_lua_tonumber = (lua_tonumber_t)GetProcAddress(hExe, "lua_tonumber");
    my_lua_tolstring = (lua_tolstring_t)GetProcAddress(hExe, "lua_tolstring");
    my_lua_type = (lua_type_t)GetProcAddress(hExe, "lua_type");
    my_lua_pushinteger = (lua_pushinteger_t)GetProcAddress(hExe, "lua_pushinteger");
    my_lua_pushboolean = (lua_pushboolean_t)GetProcAddress(hExe, "lua_pushboolean");
    my_lua_pushstring = (lua_pushstring_t)GetProcAddress(hExe, "lua_pushstring");
    my_lua_pushnil = (lua_pushnil_t)GetProcAddress(hExe, "lua_pushnil");
    my_lua_createtable = (lua_createtable_t)GetProcAddress(hExe, "lua_createtable");
    my_lua_setfield = (lua_setfield_t)GetProcAddress(hExe, "lua_setfield");
    my_lua_pushcclosure = (lua_pushcclosure_t)GetProcAddress(hExe, "lua_pushcclosure");
    my_luaL_argerror = (luaL_argerror_t)GetProcAddress(hExe, "luaL_argerror");
    
    if (!my_lua_tonumber || !my_lua_tolstring || !my_lua_type ||
        !my_lua_pushinteger || !my_lua_pushboolean || !my_lua_pushstring ||
        !my_lua_pushnil || !my_lua_createtable || !my_lua_setfield ||
        !my_lua_pushcclosure || !my_luaL_argerror) {
        return 0;  /* Failed to load functions */
    }
    #endif
    return 1;
}

/* Lua 5.1 compatible integer check using function pointers */
static int luaL_checkint_compat(lua_State *L, int arg) {
    double d = my_lua_tonumber(L, arg);
    if (d == 0 && my_lua_type(L, arg) != LUA_TNUMBER) {
        my_luaL_argerror(L, arg, "number expected");
    }
    return (int)d;
}

static const char* luaL_checkstring_compat(lua_State *L, int arg) {
    const char *s = my_lua_tolstring(L, arg, NULL);
    if (!s) my_luaL_argerror(L, arg, "string expected");
    return s;
}

static const char* luaL_checklstring_compat(lua_State *L, int arg, size_t *len) {
    const char *s = my_lua_tolstring(L, arg, len);
    if (!s) my_luaL_argerror(L, arg, "string expected");
    return s;
}

static int l_udp_new(lua_State *L) {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        my_lua_pushnil(L);
        my_lua_pushstring(L, "socket creation failed");
        return 2;
    }
    my_lua_pushinteger(L, sock);
    return 1;
}

static int l_udp_sendto(lua_State *L) {
    int sock = luaL_checkint_compat(L, 1);
    size_t msg_len;
    const char *msg = luaL_checklstring_compat(L, 2, &msg_len);
    const char *ip = luaL_checkstring_compat(L, 3);
    int port = luaL_checkint_compat(L, 4);
    
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((unsigned short)port);
    addr.sin_addr.s_addr = inet_addr(ip);
    
    int result = sendto(sock, msg, (int)msg_len, 0,
                       (struct sockaddr*)&addr, sizeof(addr));
    
    if (result < 0) {
        my_lua_pushnil(L);
        my_lua_pushstring(L, "sendto failed");
        return 2;
    }
    
    my_lua_pushboolean(L, 1);
    my_lua_pushinteger(L, result);
    return 2;
}

static int l_udp_close(lua_State *L) {
    int sock = luaL_checkint_compat(L, 1);
    CLOSE_SOCKET(sock);
    my_lua_pushboolean(L, 1);
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
    
    my_lua_pushboolean(L, 1);
    return 1;
}

/* Lua 5.1 module initialization */
__declspec(dllexport) int luaopen_minisocket(lua_State *L) {
#ifdef _WIN32
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif
    
    /* Initialize Lua function pointers */
    if (!init_lua_functions(L)) {
        my_lua_pushnil(L);
        return 1;
    }
    
    /* Manual registration for Lua 5.1 */
    my_lua_createtable(L, 0, 4);
    
    my_lua_pushcclosure(L, l_udp_new, 0);
    my_lua_setfield(L, -2, "udp_new");
    
    my_lua_pushcclosure(L, l_udp_sendto, 0);
    my_lua_setfield(L, -2, "udp_sendto");
    
    my_lua_pushcclosure(L, l_udp_close, 0);
    my_lua_setfield(L, -2, "udp_close");
    
    my_lua_pushcclosure(L, l_udp_settimeout, 0);
    my_lua_setfield(L, -2, "udp_settimeout");
    
    return 1;
}