"""Inspect lossless audio and verify decoded PCM equivalence."""

from ._version import __version__
from .core import AudioInfo, Comparison, Verification, VerificationError, compare, probe, verify

__all__ = [
    "AudioInfo",
    "Comparison",
    "Verification",
    "VerificationError",
    "compare",
    "probe",
    "verify",
    "__version__",
]
