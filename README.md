# Samery Audio

A Python library for inspecting local lossless audio and verifying audio conversions. Extracted from Samery's PCM verification tool.

## Install

Use Python 3.10 or newer and install FFmpeg with FFprobe. On macOS with Homebrew, run `brew install ffmpeg`. On Ubuntu, run `sudo apt install ffmpeg`.

Install from GitHub with Git available.

```sh
python -m pip install "git+https://github.com/omidalighadr/samery-audio.git"
```

From a local checkout, run:

```sh
python -m pip install .
```

## Python API

```python
from samery_audio import VerificationError, compare, probe

try:
    info = probe("original.m4a")
    print(info.codec, info.bit_depth, info.sample_rate, info.channels)

    report = compare("original.m4a", "converted.flac", timeout=120)
    print(report.equivalent)
    print(report.differences)
except VerificationError as error:
    print(error)
```

Both functions accept an explicit `ffprobe` executable path. `compare` also accepts an `ffmpeg` path. The timeout applies separately to each subprocess.

## Command line

```sh
samery-audio inspect "song.flac"
samery-audio compare "original.m4a" "converted.flac" --json
python -m samery_audio inspect "song.flac" --json
```

Exit codes are 0 for a completed inspection or equivalent comparison, 1 for different audio, and 2 for a verification error.

## What is checked

The first audio stream must use FLAC, ALAC or signed integer PCM in a supported WAV/AIFF container, with 16, 24 or 32 bits per sample. Comparisons require identical bit depth, sample rate, channel count, channel layout and decoded sample hashes. Multichannel audio needs a known layout.

FFmpeg decodes samples as signed 32-bit little-endian PCM and computes SHA-256 incrementally. No sample rate or channel conversion is requested. Input fingerprints are checked before and after comparison to catch concurrent changes. Images and text tags do not participate in the comparison.

A successful result establishes equivalence under these checks. It cannot establish a recording's original provenance or detect every earlier lossy conversion. AAC, MP3, floating-point PCM and unsupported bit depths produce a verification error.

Only local files are accepted. FFmpeg is restricted to its `file` and `pipe` protocols. Decoder errors produce a verification error.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests generate short waveforms locally and exercise ALAC and FLAC conversions, altered samples, rates, channel counts, corrupted files, and command-line reports.

[FFmpeg hash muxer documentation](https://ffmpeg.org/ffmpeg-formats.html#hash)
