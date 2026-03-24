# fs-pyutils

[![PyPI version](https://img.shields.io/pypi/v/fs-pyutils.svg)](https://pypi.org/project/fs-pyutils/)
[![Python](https://img.shields.io/pypi/pyversions/fs-pyutils.svg)](https://pypi.org/project/fs-pyutils/)
[![PyPI status](https://img.shields.io/pypi/status/fs-pyutils.svg)](https://pypi.org/project/fs-pyutils/)

Small Python utilities for the `fseasy` scope.

## Installation

```bash
uv add fs-pyutils
```

Or with `pip`:

```bash
pip install fs-pyutils
```

## What It Does

`fs-pyutils` provides lightweight reusable Python helpers that can be shared across projects.

Please note that we didn't install necessary dependencies for the utils as it should be installed in your main repo.

## Features

- Build structured logging helpers for syslog-based deployments.
- Add Gunicorn logging helpers for JSON/syslog output.
- Provide `systemd` notify helpers for FastAPI services and DB watchdog integration.
- Import a Python module directly from a file path.
- Convert audio bytes to MP3 bytes with `ffmpeg`.

## Usage

```python
from fs_pyutils.import import import_module_from_path

module = import_module_from_path("local_conf", "./conf.py")
```

```python
from fs_pyutils.audio import audio_to_mp3_bytes

mp3_bytes = audio_to_mp3_bytes(audio_bytes)
```

## PyPI

Project page: https://pypi.org/project/fs-pyutils/
