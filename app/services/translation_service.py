import os
import json
import time
import logging
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)


DEFAULT_SOURCE = "auto"
DEFAULT_TARGET = "iw"
BATCH_SIZE = 20  


class TranslationService:
    def __init__(self, source=DEFAULT_SOURCE, target=DEFAULT_TARGET):
        self.source = source
        self.target = target
        self.translator = GoogleTranslator(source=source, target=target)

    def translate_text(self, text: str) -> str:
        if not text:
            return ""
        return self._translate_with_retry(text)

    def translate_segments(self, segments, output_path=None, target_lang=DEFAULT_TARGET, storage_manager=None):
        if not segments:
            return []

        if target_lang != self.target:
            self.target = target_lang
            self.translator = GoogleTranslator(source=self.source, target=target_lang)

        if output_path and os.path.exists(output_path):
            logger.info(f"[CACHE] Translation found: {output_path}")
            if storage_manager:
                storage_manager.touch_file(output_path)
            return self._load_from_cache(output_path)

        logger.info(f"[API] Translating {len(segments)} segments via Google Translator...")

        translated_list = self._translate_segments_in_batches(segments)

        if output_path:
            self._save_cache(translated_list, output_path)

        return translated_list

    def _translate_segments_in_batches(self, segments: list) -> list:
        
        translated_list = []

        for i in range(0, len(segments), BATCH_SIZE):
            batch = segments[i:i + BATCH_SIZE]
            texts = [seg.get("text", "") for seg in batch]

            separator = " ||| "
            joined = separator.join(texts)

            try:
                translated_joined = self._translate_with_retry(joined)
                translated_texts = translated_joined.split(separator)

                if len(translated_texts) != len(batch):
                    logger.warning(f"[BATCH] Split mismatch at batch {i}, falling back to single translation")
                    translated_texts = [self.translate_text(t) for t in texts]

            except Exception as e:
                logger.warning(f"[BATCH] Batch translation failed: {e}, falling back to single")
                translated_texts = [self.translate_text(t) for t in texts]

            for seg, translated_text in zip(batch, translated_texts):
                translated_list.append({**seg, "text": translated_text.strip()})

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
                    logger.warning(f"[RETRY {attempt + 1}] Translation failed, retrying in {delay}s... Error: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"[ERROR] Translation failed after {retries} attempts. Returning original text.")
                    return text


if __name__ == "__main__":
    service = TranslationService()
    test_data = [{"start": 0.0, "end": 2.0, "text": "I love programming"}]
    result = service.translate_segments(test_data, "storage/test_cache.json")
    print(result)
