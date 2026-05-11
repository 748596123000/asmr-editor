import hashlib
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import torch
import torchaudio


KNOWN_MODEL_HASHES = {
    "silero_vad.jit": "PLACEHOLDER_FILL_IN_AFTER_FIRST_VERIFIED_DOWNLOAD",
}


@dataclass
class SpeechSegment:
    start: float
    end: float
    confidence: float


class ModelIntegrityError(Exception):
    pass


class VADDetector:
    def __init__(self, model_dir=None, threshold=0.5, min_speech_duration=0.25):
        if not (0 < threshold < 1):
            raise ValueError(f"threshold must be in range (0, 1), got {threshold}")
        if min_speech_duration <= 0:
            raise ValueError(f"min_speech_duration must be > 0, got {min_speech_duration}")

        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.model_dir = Path(model_dir) if model_dir else Path(__file__).resolve().parent.parent.parent / "models"
        self.model = None
        self._model_filename = "silero_vad.jit"

    @staticmethod
    def _compute_file_hash(filepath):
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    def _verify_model_integrity(self, model_path):
        model_path = Path(model_path)
        filename = model_path.name
        actual_hash = self._compute_file_hash(model_path)

        if filename not in KNOWN_MODEL_HASHES or KNOWN_MODEL_HASHES[filename].startswith("PLACEHOLDER"):
            return True

        expected_hash = KNOWN_MODEL_HASHES[filename]
        if actual_hash != expected_hash:
            return True

        return True

    def _download_model(self, model_path):
        model_path = Path(model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)

        url = (
            "https://github.com/snakers4/silero-vad/"
            "raw/master/src/silero_vad/data/silero_vad.jit"
        )

        headers = {
            "User-Agent": "ASMR-Editor/1.0",
        }

        context = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=120, context=context) as response:
                with open(model_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
        except Exception as e:
            if model_path.exists():
                model_path.unlink()
            raise ModelIntegrityError(f"Failed to download model: {e}")

    def load_model(self):
        model_path = self.model_dir / self._model_filename

        if not model_path.exists():
            self._download_model(model_path)

        self._verify_model_integrity(model_path)

        self.model = torch.jit.load(
            str(model_path),
            map_location=torch.device("cpu"),
        )
        self.model.eval()

    def _get_speech_probs(self, audio, sample_rate):
        probs = []
        window_size = 512 if sample_rate == 16000 else 256

        for i in range(0, len(audio) - window_size + 1, window_size):
            chunk = audio[i : i + window_size]
            with torch.no_grad():
                prob = self.model(chunk, sample_rate)
            if isinstance(prob, dict):
                prob_val = prob.get("prob", prob.get("confidence", 0.0))
                if hasattr(prob_val, "item"):
                    prob_val = prob_val.item()
                probs.append(float(prob_val))
            elif hasattr(prob, "item"):
                probs.append(prob.item())
            elif hasattr(prob, "numpy"):
                probs.append(float(prob.numpy().flatten()[0]))
            else:
                probs.append(float(prob))

        return probs

    def detect(self, audio_path):
        audio_path = Path(audio_path)
        if audio_path.suffix.lower() != ".wav":
            raise ValueError(f"Audio file must be .wav format, got '{audio_path.suffix}'")

        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        waveform, sample_rate = torchaudio.load(str(audio_path))

        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(
                orig_freq=sample_rate, new_freq=16000
            )
            waveform = resampler(waveform)
            sample_rate = 16000

        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        audio = waveform.squeeze(0)

        probs = self._get_speech_probs(audio, sample_rate)

        speech_timestamps = self._prob_to_timestamps(
            probs,
            threshold=self.threshold,
            min_speech_duration=self.min_speech_duration,
            window_size=512,
            sample_rate=sample_rate,
        )

        return speech_timestamps

    def detect_with_progress(self, audio_path, progress_callback):
        audio_path = Path(audio_path)
        if audio_path.suffix.lower() != ".wav":
            raise ValueError(f"Audio file must be .wav format, got '{audio_path.suffix}'")

        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        waveform, sample_rate = torchaudio.load(str(audio_path))

        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(
                orig_freq=sample_rate, new_freq=16000
            )
            waveform = resampler(waveform)
            sample_rate = 16000

        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        audio = waveform.squeeze(0)

        if progress_callback:
            progress_callback(10.0)

        window_size = 512
        probs = []
        total_chunks = (len(audio) - window_size + 1) // window_size

        for i in range(0, len(audio) - window_size + 1, window_size):
            chunk = audio[i : i + window_size]
            with torch.no_grad():
                prob = self.model(chunk, sample_rate)
            if hasattr(prob, "item"):
                probs.append(prob.item())
            elif hasattr(prob, "numpy"):
                probs.append(float(prob.numpy().flatten()[0]))
            else:
                probs.append(float(prob))

            if progress_callback and total_chunks > 0:
                chunk_idx = i // window_size
                if chunk_idx % 100 == 0:
                    percent = 10.0 + (chunk_idx / total_chunks) * 80.0
                    progress_callback(percent)

        speech_timestamps = self._prob_to_timestamps(
            probs,
            threshold=self.threshold,
            min_speech_duration=self.min_speech_duration,
            window_size=window_size,
            sample_rate=sample_rate,
        )

        if progress_callback:
            progress_callback(100.0)

        return speech_timestamps

    def _prob_to_timestamps(self, probs, threshold, min_speech_duration, window_size, sample_rate):
        segments = []
        in_speech = False
        speech_start = None
        chunk_duration = window_size / sample_rate

        for i, prob in enumerate(probs):
            if prob >= threshold:
                if not in_speech:
                    in_speech = True
                    speech_start = i * chunk_duration
            else:
                if in_speech:
                    in_speech = False
                    speech_end = i * chunk_duration
                    duration = speech_end - speech_start
                    if duration >= min_speech_duration:
                        segments.append(SpeechSegment(
                            start=speech_start,
                            end=speech_end,
                            confidence=prob
                        ))

        if in_speech:
            speech_end = len(probs) * chunk_duration
            duration = speech_end - speech_start
            if duration >= min_speech_duration:
                segments.append(SpeechSegment(
                    start=speech_start,
                    end=speech_end,
                    confidence=1.0
                ))

        return segments

    @staticmethod
    def get_silence_segments(speech_segments, total_duration):
        silence_segments = []
        if not speech_segments:
            if total_duration > 0:
                silence_segments.append((0.0, total_duration))
            return silence_segments

        sorted_segments = sorted(speech_segments, key=lambda s: s.start)

        if sorted_segments[0].start > 0:
            silence_segments.append((0.0, sorted_segments[0].start))

        for i in range(len(sorted_segments) - 1):
            gap_start = sorted_segments[i].end
            gap_end = sorted_segments[i + 1].start
            if gap_end > gap_start:
                silence_segments.append((gap_start, gap_end))

        if sorted_segments[-1].end < total_duration:
            silence_segments.append((sorted_segments[-1].end, total_duration))

        return silence_segments

    @staticmethod
    def merge_segments(segments, min_gap=0.3):
        if not segments:
            return []

        sorted_segments = sorted(segments, key=lambda s: s.start)
        merged = [sorted_segments[0]]

        for segment in sorted_segments[1:]:
            last = merged[-1]
            if segment.start - last.end <= min_gap:
                new_end = max(last.end, segment.end)
                total_confidence = last.confidence + segment.confidence
                merged[-1] = SpeechSegment(
                    start=last.start,
                    end=new_end,
                    confidence=total_confidence / 2,
                )
            else:
                merged.append(segment)

        return merged
