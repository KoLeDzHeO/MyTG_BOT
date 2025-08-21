from .gpt_handler import get_handlers as _gpt_handlers
from .trigger_handler import get_handlers as _trigger_handlers


def get_handlers():
    return _gpt_handlers() + _trigger_handlers()

