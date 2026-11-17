# Contributing

Install Python 3.10+, FFmpeg and FFprobe. From a checkout, create a virtual environment and run `python -m pip install ".[dev]"`.

Before submitting a pull request:

```sh
ruff check .
ruff format --check .
mypy
python -m unittest discover -s tests -v
python -m build
```

Include a regression test for changed behavior. Generate test audio locally: do not commit songs, account credentials, personal paths or downloaded media. Preserve the explicit integer PCM contract and the CLI's exit codes. Document any change to public report fields or error codes.

For bug reports, include the Python and FFmpeg versions, operating system, error code and a minimal reproduction with generated audio when possible. Review full tracebacks and decoder logs for private paths or metadata before sharing them.
