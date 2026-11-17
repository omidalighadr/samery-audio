"""Inspect lossless audio and verify decoded PCM equivalence."""

from ._version import __version__
from .core import AudioInfo, Comparison, VerificationError, compare, probe

__all__ = ["AudioInfo", "Comparison", "VerificationError", "compare", "probe", "__version__"]
