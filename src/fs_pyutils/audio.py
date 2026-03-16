import subprocess
import shutil


def audio_to_mp3_bytes(
    audio_bytes: bytes,
    bitrate: str = "128k",  #
    sample_rate: int | None = None,
    channels: int | None = None,
    ffmpeg_bin_path: str | None = None,
) -> bytes:
    """Any audio bytes to mp3 bytes
    Args:
    - bitrate: like  64k 96k 128k 192k
    - sample_rate: like 16000 22050 24000 44100
    - channels: like 1, 2
    - ffmpeg_bin_path: default = "ffmpeg"
    """
    ffmpeg_bin_path = ffmpeg_bin_path or "ffmpeg"
    if not shutil.which(ffmpeg_bin_path):
        raise RuntimeError("No ffmpeg found in env")

    cmd = [ffmpeg_bin_path, "-i", "pipe:0", "-codec:a", "libmp3lame", "-b:a", bitrate]

    if sample_rate:
        cmd += ["-ar", str(sample_rate)]

    if channels:
        cmd += ["-ac", str(channels)]

    cmd += ["-f", "mp3", "pipe:1"]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    out, err = proc.communicate(audio_bytes)

    if proc.returncode != 0:
        raise RuntimeError(err.decode())

    return out
