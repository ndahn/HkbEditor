import logging

from .behavior import HavokBehavior
from .hkb_types import HkbArray


def fix_variable_defaults(behavior: HavokBehavior):
    """Up to v0.7.1 HkbEditor was not updating the variable defaults array.
    """

    words: HkbArray = behavior._variable_defaults["wordVariableValues"]
    missing = len(behavior._variables) - len(words)
    if missing <= 0:
        # We have a default for each variable, nothing to do
        print("### VERSION UPDATE nothing to do", missing)
        return

    logger = logging.getLogger()
    logger.info(f"Version update: Generating missing defaults for {missing} variables")

    for idx in range(len(words), len(behavior._variables)):
        default = behavior.set_variable_default(idx, 0)
        logger.info(f" - {behavior.get_variable_name(idx)}: {default}")
