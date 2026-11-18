"""Integration tests generate their own audio; no downloads or account required."""

from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from samery_audio import core as pcm_verify
from samery_audio.cli import main as cli_main


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and FFprobe required"
)
class PCMIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wav(self, name="source.wav", *, bits=16, rate=44100, channels=2, changed=False):
        path = self.root / name
        frames = bytearray()
        for index in range(4096):
            for channel in range(channels):
                value = int(
                    math.sin(index * (0.031 + channel * 0.019)) * ((1 << (bits - 1)) - 1) * 0.7
                )
                if changed and index == 100 and channel == 0:
                    value += 1
                frames.extend(value.to_bytes(bits // 8, "little", signed=True))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(bits // 8)
            output.setframerate(rate)
            output.writeframes(bytes(frames))
        return path

    def convert(self, source, name, *options):
        output = self.root / name
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                *options,
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output

    def test_alac_to_flac_preserves_16_and_24_bit_mono_and_stereo(self):
        for bits in (16, 24):
            for rate in (44100, 48000):
                for channels in (1, 2):
                    with self.subTest(bits=bits, rate=rate, channels=channels):
                        wav = self.wav(bits=bits, rate=rate, channels=channels)
                        alac = self.convert(wav, "source.m4a", "-c:a", "alac")
                        flac = self.convert(alac, "candidate.flac", "-c:a", "flac")
                        report = pcm_verify.compare(alac, flac)
                        self.assertTrue(report.equivalent)
                        self.assertEqual(report.source.bit_depth, bits)
                        self.assertEqual(report.source_sha256, report.candidate_sha256)

    def test_verify_supported_files_without_reference(self):
        source = self.wav(bits=24)
        expected = pcm_verify.compare(source, source).source_sha256
        files = [
            source,
            self.convert(source, "verify.flac", "-c:a", "flac"),
            self.convert(source, "verify.m4a", "-c:a", "alac"),
            self.convert(source, "verify.aiff", "-c:a", "pcm_s24be"),
        ]
        for path in files:
            with self.subTest(container=path.suffix):
                report = pcm_verify.verify(path)
                self.assertEqual(report.pcm_sha256, expected)
                self.assertEqual(report.audio.bit_depth, 24)
                self.assertEqual(report.audio.sample_rate, 44100)

    def test_verify_cli_json_report(self):
        source = self.wav()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli_main(["verify", str(source), "--json"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["audio"]["codec"], "pcm_s16le")
        self.assertEqual(report["pcm_sha256"], pcm_verify.verify(source).pcm_sha256)

    def test_verify_cli_human_report(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli_main(["verify", str(self.wav())])
        self.assertEqual(code, 0)
        self.assertIn("PASS:", output.getvalue())
        self.assertIn("PCM SHA-256:", output.getvalue())

    def test_verify_cli_errors_are_structured(self):
        damaged = self.root / "damaged.wav"
        damaged.write_bytes(self.wav().read_bytes()[:-3])
        for path, expected in [
            (self.root / "missing.flac", "file_not_found"),
            (damaged, "decode_failed"),
        ]:
            with (
                self.subTest(expected=expected),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code = cli_main(["verify", str(path), "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["code"], expected)
            self.assertNotIn(str(self.root), output.getvalue())

    def test_verify_rejects_input_changed_or_deleted_during_decode(self):
        for action, expected in [("modify", "input_changed"), ("delete", "file_access_error")]:
            source = self.wav()

            def change_input(*args, action=action, source=source, **kwargs):
                if action == "modify":
                    source.write_bytes(source.read_bytes() + b"changed")
                else:
                    source.unlink()
                return "1" * 64

            with (
                self.subTest(action=action),
                patch.object(pcm_verify, "pcm_sha256", side_effect=change_input),
            ):
                with self.assertRaises(pcm_verify.VerificationError) as error:
                    pcm_verify.verify(source)
            self.assertEqual(error.exception.code, expected)

    def test_verify_custom_executables_and_missing_decoder(self):
        source = self.wav()
        report = pcm_verify.verify(
            source, ffmpeg=shutil.which("ffmpeg"), ffprobe=shutil.which("ffprobe")
        )
        self.assertEqual(report.audio.channels, 2)
        with self.assertRaises(pcm_verify.VerificationError) as error:
            pcm_verify.verify(source, ffmpeg="this-decoder-does-not-exist")
        self.assertEqual(error.exception.code, "tool_not_found")
        self.assertEqual(error.exception.operation, "decode")

    def test_32_bit_pcm_is_preserved(self):
        source = self.wav(bits=32)
        candidate = self.wav("copy.wav", bits=32)
        report = pcm_verify.compare(source, candidate)
        self.assertTrue(report.equivalent)
        self.assertEqual(report.source.bit_depth, 32)

    def test_inspect_cli_json(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = cli_main(["inspect", str(self.wav()), "--json"])
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["sample_rate"], 44100)
        self.assertEqual(report["channels"], 2)

    def test_one_changed_sample_is_detected(self):
        report = pcm_verify.compare(self.wav(), self.wav("changed.wav", changed=True))
        self.assertFalse(report.equivalent)
        self.assertEqual(report.differences, ("decoded_pcm",))

    def test_matching_samples_at_different_rates_are_not_equivalent(self):
        report = pcm_verify.compare(self.wav(), self.wav("rate.wav", rate=48000))
        self.assertEqual(report.source_sha256, report.candidate_sha256)
        self.assertEqual(report.differences, ("sample_rate",))

    def test_channel_count_change_is_detected(self):
        report = pcm_verify.compare(self.wav(), self.wav("mono.wav", channels=1))
        self.assertIn("channels", report.differences)

    def test_metadata_does_not_change_pcm_equivalence(self):
        source = self.convert(self.wav(), "source.flac", "-c:a", "flac")
        tagged = self.convert(
            source,
            "tagged.flac",
            "-c:a",
            "copy",
            "-metadata",
            "title=Different metadata",
        )
        self.assertTrue(pcm_verify.compare(source, tagged).equivalent)

    def test_lossy_source_is_rejected(self):
        source = self.wav()
        lossy = self.convert(source, "lossy.m4a", "-c:a", "aac")
        with self.assertRaises(pcm_verify.VerificationError):
            pcm_verify.compare(lossy, source)
        with self.assertRaises(pcm_verify.VerificationError) as error:
            pcm_verify.verify(lossy)
        self.assertEqual(error.exception.code, "unsupported_audio")

    def test_corrupt_input_is_rejected(self):
        invalid = self.root / "invalid.flac"
        invalid.write_bytes(b"not a valid audio file")
        with self.assertRaises(pcm_verify.VerificationError):
            pcm_verify.compare(self.wav(), invalid)

    def test_cli_json_and_exit_codes(self):
        source = self.wav()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli_main(["compare", str(source), str(source), "--json"]), 0)
        self.assertTrue(json.loads(output.getvalue())["equivalent"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                cli_main(
                    ["compare", str(source), str(self.wav("other.wav", changed=True)), "--json"]
                ),
                1,
            )
            self.assertEqual(
                cli_main(["compare", str(source), str(self.root / "missing.wav"), "--json"]),
                2,
            )

    def test_input_changed_mid_verification_is_rejected(self):
        source = self.wav()

        def change_input(*args, **kwargs):
            source.write_bytes(source.read_bytes() + b"changed")
            return "0" * 64

        with patch.object(pcm_verify, "pcm_sha256", side_effect=change_input):
            with self.assertRaises(pcm_verify.VerificationError):
                pcm_verify.compare(source, source)

    def test_empty_wav_cannot_pass_verification(self):
        path = self.root / "empty.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(44100)
            output.writeframes(b"")
        with self.assertRaises(pcm_verify.VerificationError) as error:
            pcm_verify.compare(path, path)
        self.assertEqual(error.exception.code, "empty_audio")
        with self.assertRaises(pcm_verify.VerificationError) as error:
            pcm_verify.verify(path)
        self.assertEqual(error.exception.code, "empty_audio")
        # Inspection explicitly describes headers, rather than claiming full verification.
        self.assertEqual(pcm_verify.probe(path).sample_rate, 44100)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli_main(["compare", str(path), str(path), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["code"], "empty_audio")

    def test_silence_with_samples_is_valid(self):
        source = self.root / "silence.wav"
        with wave.open(str(source), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(44100)
            output.writeframes(b"\0" * 4096)
        candidate = self.convert(source, "silence.flac", "-c:a", "flac")
        self.assertTrue(pcm_verify.compare(source, candidate).equivalent)

    def test_only_first_audio_stream_is_compared(self):
        source = self.wav()
        other = self.wav("other.wav", changed=True)
        multiple = self.root / "multiple.mka"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-i",
                str(other),
                "-map",
                "0:a",
                "-map",
                "1:a",
                "-c:a",
                "flac",
                str(multiple),
            ],
            check=True,
            capture_output=True,
        )
        self.assertTrue(pcm_verify.compare(source, multiple).equivalent)
        self.assertFalse(pcm_verify.compare(other, multiple).equivalent)

    def test_aiff_big_endian_preserves_samples(self):
        for bits in (16, 24, 32):
            with self.subTest(bits=bits):
                source = self.wav(bits=bits)
                aiff = self.convert(source, "candidate.aiff", "-c:a", f"pcm_s{bits}be")
                self.assertTrue(pcm_verify.compare(source, aiff).equivalent)

    def test_padding_16_to_24_bits_is_a_format_difference(self):
        source = self.wav()
        padded = self.convert(source, "padded.wav", "-c:a", "pcm_s24le")
        report = pcm_verify.compare(source, padded)
        self.assertEqual(report.source_sha256, report.candidate_sha256)
        self.assertEqual(report.differences, ("bit_depth",))

    def test_floating_point_and_8_bit_pcm_are_rejected(self):
        source = self.wav()
        for codec in ("pcm_f32le", "pcm_u8"):
            with self.subTest(codec=codec):
                unsupported = self.convert(source, "unsupported.wav", "-c:a", codec)
                with self.assertRaises(pcm_verify.VerificationError) as error:
                    pcm_verify.compare(source, unsupported)
                self.assertEqual(error.exception.code, "unsupported_audio")

    def test_six_channel_layout_and_channel_order(self):
        source = self.root / "surround.flac"
        signals = "|".join(f"0.1*sin(2*PI*{211 + channel * 97}*t)" for channel in range(6))
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"aevalsrc={signals}:s=48000:d=0.1:c=5.1",
                "-c:a",
                "flac",
                str(source),
            ],
            check=True,
            capture_output=True,
        )
        wav = self.convert(source, "surround.wav", "-c:a", "pcm_s24le")
        self.assertTrue(pcm_verify.compare(source, wav).equivalent)
        swapped = self.convert(
            source,
            "swapped.flac",
            "-af",
            "pan=5.1|c0=c1|c1=c0|c2=c2|c3=c3|c4=c4|c5=c5",
            "-c:a",
            "flac",
        )
        self.assertIn("decoded_pcm", pcm_verify.compare(source, swapped).differences)

    def test_two_minute_audio_conversion(self):
        source = self.root / "long.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=997:sample_rate=48000:duration=120",
                "-ac",
                "2",
                "-c:a",
                "pcm_s24le",
                str(source),
            ],
            check=True,
            capture_output=True,
        )
        candidate = self.convert(source, "long.flac", "-c:a", "flac")
        self.assertTrue(pcm_verify.compare(source, candidate).equivalent)

    def test_unicode_spaces_and_option_like_filename(self):
        source = self.wav("-آهنگ test.wav")
        candidate = self.convert(source, "صدای جدید.flac", "-c:a", "flac")
        self.assertTrue(pcm_verify.compare(source, candidate).equivalent)

    def test_deleted_input_raises_library_error(self):
        source = self.wav()
        candidate = self.wav("copy.wav")

        def remove_input(*args, **kwargs):
            source.unlink(missing_ok=True)
            return "1" * 64

        with patch.object(pcm_verify, "pcm_sha256", side_effect=remove_input):
            with self.assertRaises(pcm_verify.VerificationError) as error:
                pcm_verify.compare(source, candidate)
        self.assertEqual(error.exception.code, "file_access_error")

    def test_custom_executable_paths(self):
        source = self.wav()
        self.assertTrue(
            pcm_verify.compare(
                source, source, ffmpeg=shutil.which("ffmpeg"), ffprobe=shutil.which("ffprobe")
            ).equivalent
        )

    def test_truncated_pcm_is_rejected(self):
        source = self.wav()
        truncated = self.root / "truncated.wav"
        truncated.write_bytes(source.read_bytes()[:-3])
        with self.assertRaises(pcm_verify.VerificationError) as error:
            pcm_verify.compare(source, truncated)
        self.assertEqual(error.exception.code, "decode_failed")
        with self.assertRaises(pcm_verify.VerificationError) as error:
            pcm_verify.verify(truncated)
        self.assertEqual(error.exception.code, "decode_failed")

    def test_cli_human_error_does_not_include_private_path(self):
        with contextlib.redirect_stderr(io.StringIO()) as output:
            code = cli_main(["inspect", str(self.root / "private-name.wav")])
        self.assertEqual(code, 2)
        self.assertIn("file_not_found", output.getvalue())
        self.assertNotIn("private-name", output.getvalue())


class ProcessErrorTests(unittest.TestCase):
    def test_invalid_timeouts_do_not_launch_a_subprocess(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=value), patch("subprocess.run") as run:
                with self.assertRaises(pcm_verify.VerificationError):
                    pcm_verify._run(["ffmpeg"], value)
                run.assert_not_called()

    def test_missing_binary_is_clear(self):
        with self.assertRaises(pcm_verify.VerificationError):
            pcm_verify._run(["this-executable-does-not-exist"], 1)

    def test_timeout_is_clear(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 1)):
            with self.assertRaises(pcm_verify.VerificationError):
                pcm_verify._run(["ffmpeg"], 1)

    def test_decoder_error_does_not_expose_stderr(self):
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "", "private filename"),
        ):
            with self.assertRaises(pcm_verify.VerificationError) as error:
                pcm_verify._run(["ffmpeg"], 1)
        self.assertNotIn("private filename", str(error.exception))

    def test_probe_and_decode_errors_are_distinct(self):
        for operation in ("probe", "decode"):
            with (
                self.subTest(operation=operation),
                patch(
                    "subprocess.run", return_value=subprocess.CompletedProcess([], 7, "", "private")
                ),
            ):
                with self.assertRaises(pcm_verify.VerificationError) as error:
                    pcm_verify._run(["binary"], 1, operation=operation)
                self.assertEqual(error.exception.code, f"{operation}_failed")
                self.assertEqual(error.exception.operation, operation)
                self.assertEqual(error.exception.returncode, 7)
                self.assertNotIn("private", str(error.exception))

    def test_execution_permission_error_is_normalized(self):
        with patch("subprocess.run", side_effect=PermissionError("private executable")):
            with self.assertRaises(pcm_verify.VerificationError) as error:
                pcm_verify._run(["binary"], 1)
        self.assertEqual(error.exception.code, "tool_execution_failed")

    def test_invalid_metadata_is_normalized(self):
        invalid = [
            "bad json",
            "{}",
            '{"streams": []}',
            '{"streams": [null]}',
            '{"streams": [{"codec_name": []}]}',
        ]
        with tempfile.NamedTemporaryFile() as source:
            for raw in invalid:
                with self.subTest(raw=raw), patch.object(pcm_verify, "_run", return_value=raw):
                    with self.assertRaises(pcm_verify.VerificationError) as error:
                        pcm_verify.probe(source.name)
                    self.assertEqual(error.exception.code, "invalid_metadata")

    def test_multichannel_without_layout_is_rejected(self):
        metadata = {
            "streams": [
                {
                    "codec_name": "flac",
                    "sample_rate": "48000",
                    "channels": 6,
                    "bits_per_raw_sample": "24",
                }
            ]
        }
        with (
            tempfile.NamedTemporaryFile() as source,
            patch.object(pcm_verify, "_run", return_value=json.dumps(metadata)),
        ):
            with self.assertRaises(pcm_verify.VerificationError) as error:
                pcm_verify.probe(source.name)
        self.assertEqual(error.exception.code, "unknown_channel_layout")

    def test_missing_file_and_directory_have_distinct_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            for path, code in [
                (Path(directory) / "missing", "file_not_found"),
                (Path(directory), "not_a_file"),
            ]:
                with self.subTest(code=code):
                    with self.assertRaises(pcm_verify.VerificationError) as error:
                        pcm_verify.probe(path)
                    self.assertEqual(error.exception.code, code)

    def test_file_permission_error_is_normalized(self):
        with patch.object(Path, "stat", side_effect=PermissionError("private input")):
            with self.assertRaises(pcm_verify.VerificationError) as error:
                pcm_verify.probe("input.wav")
        self.assertEqual(error.exception.code, "file_access_error")
        self.assertNotIn("private input", str(error.exception))

    def test_invalid_timeout_precedes_file_access(self):
        for function, args in [
            (pcm_verify.probe, ("missing.wav",)),
            (pcm_verify.verify, ("missing.wav",)),
            (pcm_verify.compare, ("missing.wav", "missing.wav")),
        ]:
            for timeout in (0, -1, float("nan"), float("inf")):
                with self.subTest(function=function.__name__, timeout=timeout):
                    with self.assertRaises(pcm_verify.VerificationError) as error:
                        function(*args, timeout=timeout)
                    self.assertEqual(error.exception.code, "invalid_timeout")

    def test_version_command(self):
        from samery_audio import __version__

        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as error:
                cli_main(["--version"])
        self.assertEqual(error.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"samery-audio {__version__}")


if __name__ == "__main__":
    unittest.main()
