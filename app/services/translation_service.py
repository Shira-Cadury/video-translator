import os
import json
from deep_translator import GoogleTranslator

class TranslationService:
    def __init__(self, source="auto", target="iw"):
        self.translator = GoogleTranslator(source=source, target=target)

    def translate_text(self, text):
        if not text:
            return ""
        try:
            return self.translator.translate(text)
        except Exception as e:
            print(f"[WARN] Translation failed for text: {e}")
            return text

    def translate_segments(self, segments, output_path=None):
        if not segments:
            return []

        if output_path and os.path.exists(output_path):
            return self._load_from_cache(output_path)

        print("[API] Translating segments via Google Translator...")
        translated_list = []
        for segment in segments:
            hebrew_text = self.translate_text(segment.get("text", ""))
            
            translated_list.append({**segment, "text": hebrew_text})

        if output_path:
            self._save_cache(translated_list, output_path)

        return translated_list

    def _load_from_cache(self, path):
        print(f"[CACHE] Translated segments found: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to read cache: {e}")
            return None

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[SAVED] Translation cache created: {path}")
        except Exception as e:
            print(f"[ERROR] Could not save translation cache: {e}")

if __name__ == "__main__":
    service = TranslationService()
    test_data = [{"start": 0.0, "end": 2.0, "text": "I love programming"}]
    result = service.translate_segments(test_data, "storage/test_cache.json")
    print(result)