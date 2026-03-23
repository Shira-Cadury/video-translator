import os
import json
import time
import logging
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)
class TranslationService:
    def __init__(self, source="auto", target="iw"):
        self.translator = GoogleTranslator(source=source, target=target)

    def translate_text(self, text):
        if not text:
            return ""
        return self._translate_with_retry(text)
    def translate_segments(self, segments, output_path=None, target_lang="iw"):
        if not segments:
            return []

        self.translator.target = target_lang

        if output_path and os.path.exists(output_path):
            return self._load_from_cache(output_path)

        logger.info("[API] Translating segments via Google Translator...")
        translated_list = []
        for segment in segments:
            hebrew_text = self.translate_text(segment.get("text", ""))
            translated_list.append({**segment, "text": hebrew_text})

        if output_path:
            self._save_cache(translated_list, output_path)

        return translated_list

    def _load_from_cache(self, path):
        logger.info(f"[CACHE] Translated segments found: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[ERROR] Failed to read cache: {e}")
            return None

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"[SAVED] Translation cache created: {path}")
        except Exception as e:
            logger.warning(f"[ERROR] Could not save translation cache: {e}")


    def _translate_with_retry(self, text, retries=3, delay=1):
        for attempt in range(retries):
            try:
                return self.translator.translate(text)
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"[RETRY {attempt + 1}] Translation failed, retrying in {delay}s... Error:{e}")
                    time.sleep(delay)
                else:
                    logger.error(f"[ERROR] Translation failed after {retries} attempts. Returning original text.")
                    return text    


if __name__ == "__main__":
    service = TranslationService()
    test_data = [{"start": 0.0, "end": 2.0, "text": "I love programming"}]
    result = service.translate_segments(test_data, "storage/test_cache.json")
    print(result)