# Samery Audio

Inspect local lossless audio and check whether a conversion preserved its decoded samples and format properties. Available as a typed Python API and a command-line tool. Extracted from Samery's PCM verification tool.

For example, compare an ALAC source with a FLAC conversion before delivering it. The result describes decoded audio equivalence; it does not certify the recording's origin or detect every earlier lossy conversion.

## Install

Requires **Python 3.10+**, **FFmpeg** and **FFprobe**. There are no Python runtime dependencies.

Install FFmpeg with `brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Ubuntu, or `choco install ffmpeg` on Windows with Chocolatey. Restart your terminal if PATH changed. Confirm both programs are available:

```sh
ffmpeg -version
ffprobe -version
```

Install the library in a virtual environment (Git is required for this installation):

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install "git+https://github.com/omidalighadr/samery-audio.git"
samery-audio --version
```

From a local checkout, use `python -m pip install .`. This project is currently distributed through GitHub; `pip install samery-audio` from PyPI is not the documented installation route.

## Command line

```sh
samery-audio inspect "song.flac"
samery-audio compare "original.m4a" "converted.flac" --json
samery-audio compare "original.m4a" "converted.flac" --timeout 600
python -m samery_audio inspect "song.flac" --json
```

`inspect` reads the first audio stream's metadata. It does **not** decode the whole file or establish that the file contains playable samples. `compare` decodes both files and rejects an empty decoded stream.

| Exit code | Meaning |
| --- | --- |
| 0 | Metadata inspection succeeded, or comparison found equivalent audio |
| 1 | Both inputs were decoded, but their samples or format properties differ |
| 2 | Verification failed, or command arguments were invalid |

`--json` prints successful reports and verification errors to stdout. Human-readable verification errors go to stderr. Argument-parsing errors use argparse's ordinary stderr output.

## Python API

```python
from samery_audio import VerificationError, compare, probe

try:
    info = probe("original.m4a")
    print(info.codec, info.bit_depth, info.sample_rate, info.channels)

    report = compare("original.m4a", "converted.flac", timeout=120)
    if report.equivalent:
        print("Conversion preserved the audio samples and format properties.")
    else:
        print("Differences:", report.differences)
except VerificationError as error:
    print(error.code, str(error))
```

Both functions accept a custom `ffprobe` executable path. `compare` also accepts an `ffmpeg` executable path:

```python
report = compare(
    "original.m4a",
    "converted.flac",
    ffmpeg="/path/to/ffmpeg",
    ffprobe="/path/to/ffprobe",
    timeout=600,
)
```

`timeout` must be finite and positive. It applies **separately to each subprocess**, not to the entire comparison. A comparison invokes two probes and two decoders, so its total runtime can approach four times this value. The API is synchronous; in an async application, run it in a worker thread rather than blocking the event loop.

`AudioInfo` and `Comparison` are immutable dataclasses. `Comparison.differences` can contain `sample_rate`, `channels`, `bit_depth`, `channel_layout` and `decoded_pcm`. The source and candidate hashes describe signed 32-bit little-endian decoded PCM, not the original file bytes.

## Error handling

All expected file, subprocess and verification failures raise `VerificationError`. Use `error.code`, rather than parsing the English message. `operation` is `probe`, `decode`, or `None`; `returncode` is set when a subprocess returns a failure status.

| Code | Action |
| --- | --- |
| `file_not_found`, `not_a_file`, `file_access_error` | Check that the input is an accessible, regular local file |
| `tool_not_found`, `tool_execution_failed` | Install FFmpeg/FFprobe or correct their executable paths and permissions |
| `timeout` | Increase the per-process timeout for longer files |
| `probe_failed`, `invalid_metadata` | Check that the file contains readable audio metadata |
| `decode_failed` | Check for damaged audio or an unavailable decoder |
| `unsupported_audio`, `unknown_channel_layout` | Use a supported integer lossless format with a known layout |
| `empty_audio` | No samples were decoded; a header alone cannot pass comparison |
| `input_changed` | Stop modifying the inputs and retry |
| `invalid_timeout`, `invalid_digest` | Correct the timeout or check the FFmpeg installation |

Example JSON error:

```json
{
  "error": "No audio samples were decoded. The file may contain only a header.",
  "code": "empty_audio",
  "operation": "decode",
  "returncode": null
}
```

Messages and JSON fields omit input paths, metadata and decoder stderr. Python exception chaining retains the underlying cause for local debugging; a full traceback may therefore include local details.

## Verification contract and limits

- Only the **first audio stream** participates. Artwork, text tags, additional audio streams and video are excluded.
- Supports ALAC, FLAC and signed integer PCM (`pcm_s16le/be`, `pcm_s24le/be`, `pcm_s32le/be`) with 16, 24 or 32 bits per sample. WAV and AIFF PCM are covered by integration tests. Other containers depend on FFmpeg and are not separately guaranteed.
- Requires equal bit depth, sample rate, channel count, channel layout and decoded sample hashes. Padding 16-bit audio to 24-bit is a format difference even when its normalized samples match.
- FFmpeg is explicitly instructed to output `pcm_s32le`; no resampling or downmixing is requested. Its hash muxer computes SHA-256 incrementally, so Python does not collect the decoded audio in memory.
- AAC, MP3, floating-point PCM and unsupported bit depths are rejected. Multichannel inputs require a known layout. Silence contains samples and is valid; a stream with zero decoded samples is rejected.
- Input fingerprints are checked before and after comparison to catch ordinary concurrent file changes. This is not a file-locking mechanism or a guarantee against deliberate concurrent replacement.
- Only local regular files are accepted, with FFmpeg restricted to `file` and `pipe` protocols. Decoder-reported failures are rejected. A successful comparison does not prove that both inputs are complete relative to an external album or download manifest.
- A FLAC made from an earlier MP3 can still be a valid lossless encoding of that decoded MP3. This library cannot establish original provenance or recover discarded audio information.

## Development and checks

```sh
python -m pip install ".[dev]"
ruff check .
ruff format --check .
mypy
python -m unittest discover -s tests -v
python -m build
```

Tests generate audio locally without downloads or accounts. They cover ALAC/FLAC conversion, 16/24/32-bit PCM, big-endian AIFF, six-channel layout and channel order, changed samples, metadata changes, empty and truncated inputs, a two-minute recording, Unicode paths, errors and CLI reports. These cases do not establish performance for hour-long recordings.

CI checks formatting and types, builds both a source distribution and a wheel, and runs tests against an installed wheel on macOS, Linux and Windows with Python 3.10 and 3.13. Integration tests are skipped when FFmpeg is absent locally; CI requires both executables before running tests.

## License and references

[MIT](LICENSE). See [CHANGELOG.md](CHANGELOG.md) for version history and [CONTRIBUTING.md](CONTRIBUTING.md) for contributions.

- [FFmpeg hash muxer](https://ffmpeg.org/ffmpeg-formats.html#hash)
- [Python packaging guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
