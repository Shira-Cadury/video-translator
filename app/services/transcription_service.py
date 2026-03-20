import whisper
import os
import json
import time

class TranscriptionService:
    _model = None  

    def __init__(self):
        self.load_model()

    def load_model(self):
        if TranscriptionService._model is None:
            print("Loading Whisper model ('base')...")
            try:
                TranscriptionService._model = whisper.load_model("base")
                print("Model loaded.")
            except Exception as e:
                print(f"Failed to load model: {e}")
                TranscriptionService._model = None

        self.model = TranscriptionService._model

    def transcribe(self, audio_path, json_path=None):
        if json_path and os.path.exists(json_path):
            cached = self._load_from_cache(json_path)
            if cached:
                print("Using cached transcription")
                return cached

        if self.model is None:
            return {"success": False, "error": "Model not loaded"}

        if not os.path.exists(audio_path):
            return {"success": False, "error": "Audio file not found"}

        print(f"Transcribing: {audio_path}")
        start = time.time()

        try:
            result = self.model.transcribe(audio_path)

            if json_path:
                self._save_to_cache(result, json_path)

            print(f"[TIME] Transcription: {time.time() - start:.2f}s")

            return {
                **result,
                "success": True,
                "from_cache": False
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _load_from_cache(self, json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    **data,
                    "success": True,
                    "from_cache": True
                }
        except Exception:
            print("Cache corrupted, ignoring")
            return None

    def _save_to_cache(self, data, json_path):
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("Saved transcription to cache")
        except Exception as e:
            print(f"Failed to save cache: {e}")