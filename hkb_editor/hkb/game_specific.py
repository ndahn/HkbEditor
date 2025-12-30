from typing import Any

game_attributes = {
    "CustomManualSelectorGenerator": {
        "rideSync": False,  # Elden Ring
        "isBasePoseAnim": True,  # Nightreign
    },
}


def separate_game_specific_attributes(type_name: str, attributes: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of optional attributes for the given behavior node type. These attributes will be removed from the passed attributes dict.

    Parameters
    ----------
    type_name : str
        Behavior node type name.
    attributes : dict[str, Any]
        Attributes for the node type, typically used for construction.

    Returns
    -------
    dict[str, Any]
        A dict of optional attributes. Values are defaults unless present in the passed attributes dict.
    """
    optional = game_attributes.get(type_name)
    ret = {}
    if optional:
        for key, default in optional.items():
            ret[key] = attributes.pop(key, default)

    return ret
