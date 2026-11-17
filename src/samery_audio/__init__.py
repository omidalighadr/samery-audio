"""Inspect lossless audio and verify decoded PCM equivalence."""
from .core import AudioInfo, Comparison, VerificationError, compare, probe

__version__ = "0.1.0"
__all__ = ["AudioInfo", "Comparison", "VerificationError", "compare", "probe"]
