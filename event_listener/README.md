# What is this?
A small library that you can load in order to use HkbEditor's Event Listener tool. This allows you to live track which animation events a certain character currently executes.

![](screenshot.png)

# How to use this
Place the `.dll` and `.yaml` files inside your mod folder, then add the following lines to your ME3 profile:

```toml
[[native]]
path = "hkb_event_listener.dll
```

Once you start the game you may be able to spot a short message saying that events will now be published at a certain address (`127.0.0.1:27072` by default). See the yaml config for more information.
