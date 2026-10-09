"""Audio capabilities only; no text defaults, prices, keys or dispatch grants."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class AudioModelDescriptor:
    catalog_id: Literal["openai"]
    model_id: Literal["whisper-1"]
    adapter_kind: Literal["audio_transcription"]
    operation: Literal["transcribe"]
    endpoint: Literal["https://api.openai.com"]
    request_path: Literal["/v1/audio/transcriptions"]


WHISPER_TRANSCRIPTION = AudioModelDescriptor(
    "openai",
    "whisper-1",
    "audio_transcription",
    "transcribe",
    "https://api.openai.com",
    "/v1/audio/transcriptions",
)
AUDIO_MODEL_CATALOG = (WHISPER_TRANSCRIPTION,)


def get_audio_model(catalog_id: str, model_id: str) -> AudioModelDescriptor:
    if catalog_id != "openai" or model_id != "whisper-1":
        raise ValueError("unsupported audio capability")
    return WHISPER_TRANSCRIPTION
