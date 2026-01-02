# Templates
Sometimes you have a more complex task that is tedious to do by hand. Maybe you want to create 50 new clip generators. Maybe you want to rename every node inside a certain state machine. Whatever the case, templates got you covered!

![](../assets/guide/templates-1.png)

Templates are small(ish) python scripts that can automate behavior edits. Each template must have a `run()` function which takes a *TemplateContext* object as its first argument. Templates are smart in the way that all additional arguments as well as the docstring are used for generating a dialog. 

The TemplateContext object provides various methods for creating and editing objects, events, variables and animations, create variable bindings, find specific objects, and so on. The API is *mostly* stable, so the best way to learn how to write templates is by looking at the [API documentation](../../reference/hkb_editor/templates/common/#hkb_editor.templates.common.CommonActionsMixin), as well as the already included [templates](https://github.com/ndahn/HkbEditor/tree/main/templates).

???+ note

    As the names of state machines and CMSGs tend to change between games, most templates are game specific. There is some overlap between Elden Ring and Nightreign, but as of now this hasn't really been explored.
