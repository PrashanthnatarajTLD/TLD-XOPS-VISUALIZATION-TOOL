"""Per-parameter cleaning agents.

Each cleaner converts raw extracted string/number into a normalized typed series
and can be extended with parameter-specific logic.
"""

from .number_cleaners import clean_float_like

__all__ = [
    "clean_float_like",
]

