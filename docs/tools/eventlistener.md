# Event Listener
The event listener is a DLL that hooks into the game to expose the fired events. More specifically, it detours the internal `hkbFireEvent` function to print out the received event string. 

???+ info

    This tool is extremly useful when working on more complex behaviors where many behavior transitions happen in a short time, e.g. jump attacks (jump start to jump loop to jump attack to landing to running to...).
    
It also sends the string on a UDP socket which can then be visualized in HkbEditor.
