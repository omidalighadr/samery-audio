# Changelog

## 0.2.0

- Add `verify(path)` and `samery-audio verify` to decode one supported audio stream without a reference file.
- Return immutable audio properties and the decoded PCM SHA-256 digest, with JSON output from the CLI.
- Reject empty streams and decoder-reported corruption, and check that the input stayed stable while being verified.
- Reuse the existing comparison fingerprint checks without changing comparison reports or exit codes.
- Document the difference between inspecting metadata, verifying decodability and comparing two recordings.

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
