"""Compare decoded integer PCM in local lossless audio files using FFmpeg."""

from __future__ import annotations

import json
import math
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_CODECS = {
    "alac",
    "flac",
    "pcm_s16le",
    "pcm_s16be",
    "pcm_s24le",
    "pcm_s24be",
    "pcm_s32le",
    "pcm_s32be",
}


class VerificationError(Exception):
    """Verification failed; ``code`` is suitable for programmatic handling.

    Messages and structured fields omit input paths, tags and decoder stderr.
    Python exception chaining retains the original cause for local debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "verification_failed",
        operation: str | None = None,
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.operation = operation
        self.returncode = returncode


@dataclass(frozen=True)
class AudioInfo:
    codec: str
    sample_rate: int
    channels: int
    bit_depth: int
    channel_layout: str


@dataclass(frozen=True)
class Comparison:
    equivalent: bool
    source: AudioInfo
    candidate: AudioInfo
    source_sha256: str
    candidate_sha256: str
    differences: tuple[str, ...]


def _validate_timeout(timeout: float) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise VerificationError("Timeout must be finite and positive.", code="invalid_timeout")


def _run(command: list[str], timeout: float, *, operation: str = "decode") -> str:
    _validate_timeout(timeout)
    tool = "FFprobe" if operation == "probe" else "FFmpeg"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VerificationError(
            f"{tool} was not found. Install FFmpeg and FFprobe or set the executable path.",
            code="tool_not_found",
            operation=operation,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VerificationError(
            f"{tool} exceeded the timeout. Increase timeout for longer files.",
            code="timeout",
            operation=operation,
        ) from exc
    except OSError as exc:
        raise VerificationError(
            f"{tool} could not start. Check the executable path and permissions.",
            code="tool_execution_failed",
            operation=operation,
        ) from exc
    if result.returncode:
        # Decoder stderr may contain paths or metadata; do not echo it by default.
        raise VerificationError(
            (
                "FFprobe could not read the audio metadata. Check the input format and file access."
                if operation == "probe"
                else "FFmpeg could not decode the audio. Check for corruption or an unsupported decoder."
            ),
            code=f"{operation}_failed",
            operation=operation,
            returncode=result.returncode,
        )
    return result.stdout


def _local_file(value: str | Path) -> Path:
    try:
        path = Path(value).expanduser().resolve()
        info = path.stat()
    except FileNotFoundError as exc:
        raise VerificationError(
            "Input file does not exist. Check the local file path.", code="file_not_found"
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerificationError(
            "Input file cannot be accessed. Check its path and permissions.",
            code="file_access_error",
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise VerificationError("Input must be a regular local file.", code="not_a_file")
    return path


def probe(path: str | Path, *, ffprobe: str = "ffprobe", timeout: float = 300) -> AudioInfo:
    """Inspect first-stream metadata; this does not decode or validate all samples."""
    _validate_timeout(timeout)
    path = _local_file(path)
    raw = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "a:0",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        timeout,
        operation="probe",
    )
    try:
        stream = json.loads(raw)["streams"][0]
        codec = stream["codec_name"]
        if not isinstance(codec, str):
            raise ValueError("Invalid codec name")
        rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        bits = int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)
        layout = stream.get("channel_layout") or ({1: "mono", 2: "stereo"}.get(channels, "unknown"))
        if not isinstance(layout, str):
            raise ValueError("Invalid channel layout")
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise VerificationError(
            "Audio stream metadata is missing or invalid.", code="invalid_metadata"
        ) from exc
    if codec not in SUPPORTED_CODECS or bits not in (16, 24, 32) or rate <= 0 or channels <= 0:
        raise VerificationError(
            "Supported inputs are lossless integer ALAC, FLAC or PCM with 16, 24 or 32 bits.",
            code="unsupported_audio",
        )
    if channels > 2 and layout == "unknown":
        raise VerificationError(
            "Multichannel audio requires an explicit channel layout.",
            code="unknown_channel_layout",
        )
    return AudioInfo(codec, rate, channels, bits, layout)


def pcm_sha256(path: str | Path, *, ffmpeg: str = "ffmpeg", timeout: float = 300) -> str:
    """Hash signed 32-bit little-endian decoded PCM, without resampling or downmixing.

    FFmpeg's hash muxer computes the digest incrementally, so Python does not
    accumulate decoded audio in memory. Call probe() first to validate the codec.
    """
    path = _local_file(path)
    raw = _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-c:a",
            "pcm_s32le",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        timeout,
    )
    match = re.fullmatch(r"SHA256=([0-9a-fA-F]{64})\s*", raw)
    if not match:
        raise VerificationError("Unexpected FFmpeg digest output.", code="invalid_digest")
    digest = match[1].lower()
    # SHA-256 of zero bytes: a valid header alone must not pass audio verification.
    if digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855":
        raise VerificationError(
            "No audio samples were decoded. The file may contain only a header.",
            code="empty_audio",
            operation="decode",
        )
    return digest


def compare(
    source: str | Path,
    candidate: str | Path,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    timeout: float = 300,
) -> Comparison:
    """Require matching format properties AND identical decoded audio samples."""
    _validate_timeout(timeout)
    source, candidate = _local_file(source), _local_file(candidate)

    def fingerprint(path: Path) -> tuple[int, int, int, int]:
        try:
            info = path.stat()
        except OSError as exc:
            raise VerificationError(
                "An input became inaccessible during verification. Retry with stable files.",
                code="file_access_error",
            ) from exc
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    initial = fingerprint(source), fingerprint(candidate)
    first = probe(source, ffprobe=ffprobe, timeout=timeout)
    second = probe(candidate, ffprobe=ffprobe, timeout=timeout)
    differences = [
        field
        for field in ("sample_rate", "channels", "bit_depth", "channel_layout")
        if getattr(first, field) != getattr(second, field)
    ]
    first_hash = pcm_sha256(source, ffmpeg=ffmpeg, timeout=timeout)
    second_hash = pcm_sha256(candidate, ffmpeg=ffmpeg, timeout=timeout)
    if initial != (fingerprint(source), fingerprint(candidate)):
        raise VerificationError(
            "An input changed during verification; retry with stable files.",
            code="input_changed",
        )
    if first_hash != second_hash:
        differences.append("decoded_pcm")
    return Comparison(not differences, first, second, first_hash, second_hash, tuple(differences))
