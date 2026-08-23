from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from claudechat.audio.vad import SpeechGate
from claudechat.config import Config
from claudechat.engine.reply import VoiceReplyListener


class FakeCapture:
    sample_rate = 16000

    def __init__(self, data_sequence=None):
        self.started = False
        self._data_sequence = data_sequence or []
        self._index = 0
        self._stopped = False

    def start(self):
        self.started = True
        self._index = 0
        self._stopped = False

    def take(self):
        if self._index < len(self._data_sequence):
            data = self._data_sequence[self._index]
            self._index += 1
            return data
        return b""

    def stop(self):
        self._stopped = True
        # Return all data
        return b"".join(self._data_sequence)


class FakeTranscriber:
    def __init__(self, text="hello"):
        self.text = text

    def transcribe(self, pcm, sample_rate):
        return self.text


class FakeGate:
    def __init__(self, state_sequence=None):
        self._state_sequence = state_sequence or ["waiting"]
        self._index = 0
        self._state = self._state_sequence[0] if self._state_sequence else "waiting"

    def feed(self, pcm):
        self._index += 1
        if self._index < len(self._state_sequence):
            self._state = self._state_sequence[self._index]
        return self._state

    @property
    def state(self):
        return self._state

    @property
    def _state(self):
        return self.__dict__.get("__state", "waiting")

    @_state.setter
    def _state(self, value):
        self.__dict__["__state"] = value


def test_listen_once_with_no_speech_returns_empty():
    """No speech detected returns empty string."""
    config = Config()
    capture = FakeCapture([b""])
    transcriber = FakeTranscriber()

    def gate_factory():
        return FakeGate(["waiting"])

    listener = VoiceReplyListener(
        config,
        capture_factory=lambda: capture,
        transcriber_factory=lambda: transcriber,
        gate_factory=gate_factory,
        speak=MagicMock(),
    )

    result = listener.listen_once()
    assert result == ""


def test_listen_once_with_speech_transcribes_and_copies():
    """Speech detected transcribes, copies to clipboard, and speaks confirmation."""
    config = Config()
    capture = FakeCapture([b"audio_data"])
    transcriber = FakeTranscriber("hello world")
    copy_mock = MagicMock()
    speak_mock = MagicMock()

    def gate_factory():
        return FakeGate(["speech", "end"])

    listener = VoiceReplyListener(
        config,
        capture_factory=lambda: capture,
        transcriber_factory=lambda: transcriber,
        gate_factory=gate_factory,
        speak=speak_mock,
        copy_to_clipboard=copy_mock,
    )

    result = listener.listen_once()
    assert result == "hello world"
    copy_mock.assert_called_once_with("hello world")
    speak_mock.assert_called_once()
    assert "Copied" in speak_mock.call_args[0][0]


def test_listen_once_strips_control_characters():
    """Transcribed text is stripped of control characters."""
    config = Config()
    capture = FakeCapture([b"audio_data"])
    transcriber = FakeTranscriber("hello\x00world")
    copy_mock = MagicMock()

    def gate_factory():
        return FakeGate(["speech", "end"])

    listener = VoiceReplyListener(
        config,
        capture_factory=lambda: capture,
        transcriber_factory=lambda: transcriber,
        gate_factory=gate_factory,
        speak=MagicMock(),
        copy_to_clipboard=copy_mock,
    )

    result = listener.listen_once()
    assert "\x00" not in result
    assert result == "helloworld"


def test_listen_once_empty_transcription_returns_empty():
    """Empty transcription returns empty string."""
    config = Config()
    capture = FakeCapture([b"audio_data"])
    transcriber = FakeTranscriber("   ")
    speak_mock = MagicMock()

    def gate_factory():
        return FakeGate(["speech", "end"])

    listener = VoiceReplyListener(
        config,
        capture_factory=lambda: capture,
        transcriber_factory=lambda: transcriber,
        gate_factory=gate_factory,
        speak=speak_mock,
        copy_to_clipboard=MagicMock(),
    )

    result = listener.listen_once()
    assert result == ""


def test_listen_once_copy_to_clipboard_failure_returns_empty():
    """If copy_to_clipboard raises, return empty and log."""
    config = Config()
    capture = FakeCapture([b"audio_data"])
    transcriber = FakeTranscriber("hello")

    def gate_factory():
        return FakeGate(["speech", "end"])

    def copy_fail(text):
        raise RuntimeError("clipboard tool not found")

    listener = VoiceReplyListener(
        config,
        capture_factory=lambda: capture,
        transcriber_factory=lambda: transcriber,
        gate_factory=gate_factory,
        speak=MagicMock(),
        copy_to_clipboard=copy_fail,
    )

    result = listener.listen_once()
    assert result == ""


def test_listen_once_exception_returns_empty():
    """Any exception is caught and returns empty."""
    config = Config()

    def capture_factory():
        raise RuntimeError("capture failed")

    def gate_factory():
        return FakeGate()

    listener = VoiceReplyListener(
        config,
        capture_factory=capture_factory,
        transcriber_factory=lambda: FakeTranscriber(),
        gate_factory=gate_factory,
        speak=MagicMock(),
    )

    result = listener.listen_once()
    assert result == ""


def test_listen_once_lazy_loads_capture():
    """Capture is not built in __init__, only on first listen_once."""
    config = Config()
    capture_mock = MagicMock()
    capture_factory_mock = MagicMock(return_value=capture_mock)

    listener = VoiceReplyListener(
        config,
        capture_factory=capture_factory_mock,
        transcriber_factory=lambda: FakeTranscriber(),
        gate_factory=lambda: FakeGate(["waiting"]),
        speak=MagicMock(),
    )

    # Factory should not be called yet
    capture_factory_mock.assert_not_called()

    # Now call listen_once
    listener.listen_once()

    # Factory should be called now
    capture_factory_mock.assert_called_once()


def test_listen_once_lazy_loads_transcriber():
    """Transcriber is not built in __init__, only on first listen_once."""
    config = Config()
    transcriber_mock = MagicMock()
    transcriber_factory_mock = MagicMock(return_value=transcriber_mock)

    listener = VoiceReplyListener(
        config,
        capture_factory=lambda: FakeCapture([b""]),
        transcriber_factory=transcriber_factory_mock,
        gate_factory=lambda: FakeGate(["waiting"]),
        speak=MagicMock(),
    )

    # Factory should not be called yet
    transcriber_factory_mock.assert_not_called()

    # Now call listen_once
    listener.listen_once()

    # Factory should be called now
    transcriber_factory_mock.assert_called_once()


def test_listen_once_respects_voice_reply_window():
    """listen_once respects the voice_reply_window_seconds timeout."""
    config = Config(voice_reply_window_seconds=0.2)
    call_count = [0]

    def capture_factory():
        capture = FakeCapture()
        original_take = capture.take

        def take_with_count():
            call_count[0] += 1
            return original_take()

        capture.take = take_with_count
        return capture

    def gate_factory():
        return FakeGate(["waiting"])  # Never leaves "waiting"

    listener = VoiceReplyListener(
        config,
        capture_factory=capture_factory,
        transcriber_factory=lambda: FakeTranscriber(),
        gate_factory=gate_factory,
        speak=MagicMock(),
    )

    start = time.time()
    result = listener.listen_once()
    elapsed = time.time() - start

    assert result == ""
    # Should have timed out after ~0.2s (with some tolerance)
    assert elapsed >= 0.15


def test_default_copy_to_clipboard_uses_available_tool():
    """Default copy_to_clipboard tries tools in order and uses the first available."""
    config = Config()

    with patch("shutil.which") as mock_which:
        with patch("subprocess.run") as mock_run:
            # Simulate only pbcopy being available
            def which_side_effect(cmd):
                return cmd if cmd == "pbcopy" else None

            mock_which.side_effect = which_side_effect

            VoiceReplyListener._default_copy_to_clipboard("test text")

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["pbcopy"]
            assert call_args[1]["input"] == b"test text"


def test_default_copy_to_clipboard_raises_when_no_tool_found():
    """Default copy_to_clipboard raises when no tool is available."""
    config = Config()

    with patch("shutil.which", return_value=None):
        try:
            VoiceReplyListener._default_copy_to_clipboard("test text")
            raise AssertionError("expected RuntimeError")
        except RuntimeError as e:
            assert "clipboard tool" in str(e).lower()
