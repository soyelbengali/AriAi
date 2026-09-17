from types import SimpleNamespace

import core.stt as stt


class LegacyRejectingModel:
    def __init__(self):
        self.cfg = SimpleNamespace(decoding=SimpleNamespace(beam=SimpleNamespace(beam_size=4)))

    def eval(self):
        pass

    def to(self, device):
        return self

    def change_decoding_strategy(self, decode_cfg):
        self.decode_cfg = decode_cfg

    def transcribe(self, paths, **kwargs):
        if "source_lang" in kwargs or "target_lang" in kwargs or "task" in kwargs:
            raise TypeError("unexpected keyword argument")
        return [SimpleNamespace(text="hello world")]


def test_transcribe_file_removes_unsupported_canary_kwargs(monkeypatch):
    monkeypatch.setattr(stt, "_model", LegacyRejectingModel())
    monkeypatch.setattr(stt, "_load_error", None)

    result = stt.transcribe_file("/tmp/test.wav")

    assert result == "hello world"
