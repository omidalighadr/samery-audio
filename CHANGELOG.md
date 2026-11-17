# Changelog

## 0.1.1

- Reject decoded streams with zero audio samples during comparison.
- Add structured verification error codes, operation and process return status, with actionable messages that omit paths and decoder stderr.
- Normalize inaccessible files and executable launch errors into `VerificationError`.
- Validate timeouts consistently before file access in public API functions.
- Add AIFF, multichannel, two-minute audio, truncated input, Unicode path and error regression tests.
- Include Python typing metadata, a single version source and CLI `--version`.
- Add code formatting, lint and strict type checks; test built wheels in CI.
- Clarify metadata-only inspection, verification limits, timeout semantics and troubleshooting.
- Add the MIT license.

## 0.1.0

- Initial Python API and CLI for inspecting local lossless audio and comparing decoded PCM and format properties.
