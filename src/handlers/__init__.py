"""Handlers package."""

from .trigger_handler import get_handlers as _trigger_handlers
from .gpt_handler import get_handlers as _gpt_handlers

def get_handlers():
    return _trigger_handlers() + _gpt_handlers()
