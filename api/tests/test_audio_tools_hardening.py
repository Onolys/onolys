"""ffmpeg/ffprobe run with a local-file-only protocol whitelist, an explicit demuxer where
the format was sniffed, and resource limits on the subprocess."""

import resource
import subprocess
from pathlib import Path

import pytest

from onolys_api import audio, audio_child

pytestmark = pytest.mark.unit


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        if "ffmpeg" in cmd:
            Path(cmd[-1]).write_bytes(b"fLaC")
        return subprocess.CompletedProcess(cmd, 0, stdout=b'{"streams": [], "format": {}}')

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    return calls


@pytest.mark.parametrize(
    ("fmt", "demuxer"),
    [("wav", "wav"), ("mp3", "mp3"), ("ogg", "ogg"), ("m4a", "mov"), ("webm", "matroska,webm")],
)
def test_whitelist_and_explicit_demuxer(captured, tmp_path, fmt, demuxer):
    tools = audio.FfmpegTools()
    src = tmp_path / "in.bin"
    src.write_bytes(b"x")
    tools.probe(src, fmt)
    tools.to_flac(src, tmp_path / "out.flac", None, fmt)
    for cmd, kw in captured:
        assert cmd[cmd.index("-protocol_whitelist") + 1] == "file"
        assert cmd[cmd.index("-f") + 1] == demuxer
        assert cmd.index("-f") < cmd.index(str(src))  # an input option, before -i / the path
        assert "preexec_fn" not in kw
        assert "onolys_api.audio_child" in cmd


def test_no_demuxer_flag_when_format_unknown(captured, tmp_path):
    src = tmp_path / "in.bin"
    src.write_bytes(b"x")
    audio.FfmpegTools().probe(src)
    cmd = captured[0][0]
    assert "-f" not in cmd and "-protocol_whitelist" in cmd


def test_rlimits_are_applied_in_the_child(monkeypatch):
    seen = {}
    monkeypatch.setattr(resource, "setrlimit", lambda which, lim: seen.__setitem__(which, lim))
    audio_child._limit_child()
    assert {resource.RLIMIT_CPU, resource.RLIMIT_AS, resource.RLIMIT_FSIZE} <= set(seen)


def test_audio_child_applies_limits_before_exec():
    import json
    import sys

    script = "import json,resource; print(json.dumps([resource.getrlimit(resource.RLIMIT_CPU), resource.getrlimit(resource.RLIMIT_NOFILE)]))"
    result = subprocess.run([sys.executable, "-m", "onolys_api.audio_child",
                             sys.executable, "-c", script],
                            capture_output=True, check=True, timeout=2)
    assert json.loads(result.stdout) == [[audio_child._CPU_LIMIT_S] * 2, [audio_child._OPEN_FILES] * 2]
