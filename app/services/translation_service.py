import os
import json
import time
import logging
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = "auto"
DEFAULT_TARGET = "iw"


MAX_BATCH_CHARS = 3000
BATCH_SIZE = 20


class TranslationService:
    def __init__(self, source=DEFAULT_SOURCE, target=DEFAULT_TARGET):
        self.source = source
        self.target = target
        self.translator = GoogleTranslator(source=source, target=target)

    def translate_text(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        return self._translate_with_retry(text)

    def translate_segments(self, segments, output_path=None, target_lang=DEFAULT_TARGET, storage_manager=None):
        if not segments:
            logger.warning("[TRANSLATION] No segments to translate, returning empty list")
            return []

        if target_lang == "iw":
            target_lang = "he"

        google_lang = "iw" if target_lang == "he" else target_lang
        if google_lang != self.target:
            self.target = google_lang
            self.translator = GoogleTranslator(source=self.source, target=google_lang)

        if output_path and os.path.exists(output_path):
            logger.info(f"[CACHE] Translation found: {output_path}")
            if storage_manager:
                storage_manager.touch_file(output_path)
            cached = self._load_from_cache(output_path)
            if cached is not None:
                return cached
            logger.warning("[TRANSLATION] Cache read failed, re-translating...")

        logger.info(f"[TRANSLATION] Translating {len(segments)} segments → '{target_lang}'")

        try:
            translated_list = self._translate_segments_in_batches(segments)
        except Exception as e:
            logger.error(f"[TRANSLATION] Fatal error during translation: {e}")
            logger.warning("[TRANSLATION] Returning original (untranslated) segments as fallback")
            return segments

        if not translated_list:
            logger.error("[TRANSLATION] Got empty result — returning original segments")
            return segments

        if output_path:
            self._save_cache(translated_list, output_path)

        return translated_list

    def _translate_segments_in_batches(self, segments: list) -> list:
        translated_list = []
        separator = " ||| "

        batch = []
        batch_chars = 0

        def flush_batch(b):
            if not b:
                return []
            texts = [seg.get("text", "").strip() for seg in b]
            joined = separator.join(texts)

            logger.debug(f"[BATCH] Sending {len(b)} segments, {len(joined)} chars")

            try:
                translated_joined = self._translate_with_retry(joined)

                if translated_joined is None:
                    raise ValueError("Translator returned None")

                translated_texts = translated_joined.split(separator)

                if len(translated_texts) != len(b):
                    logger.warning(
                        f"[BATCH] Split mismatch: sent {len(b)}, got {len(translated_texts)}. "
                        f"Falling back to one-by-one."
                    )
                    translated_texts = [self._safe_translate_one(t) for t in texts]

            except Exception as e:
                logger.warning(f"[BATCH] Batch failed ({e}), falling back to one-by-one")
                texts = [seg.get("text", "").strip() for seg in b]
                translated_texts = [self._safe_translate_one(t) for t in texts]

            result = []
            for seg, translated_text in zip(b, translated_texts):
                result.append({
                    **seg,
                    "text": translated_text.strip() if translated_text else seg.get("text", "")
                })
            return result

        for seg in segments:
            text = seg.get("text", "").strip()
            seg_chars = len(text) + len(separator)

            if batch and (batch_chars + seg_chars > MAX_BATCH_CHARS):
                translated_list.extend(flush_batch(batch))
                batch = []
                batch_chars = 0

            if seg_chars > MAX_BATCH_CHARS:
                translated_list.extend(flush_batch([seg]))
            else:
                batch.append(seg)
                batch_chars += seg_chars

        if batch:
            translated_list.extend(flush_batch(batch))

        return translated_list

    def _safe_translate_one(self, text: str) -> str:
        if not text or not text.strip():
            return text
        try:
            result = self._translate_with_retry(text)
            return result if result else text
        except Exception as e:
            logger.warning(f"[TRANSLATION] Single segment failed: {e}")
            return text

    def _load_from_cache(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    logger.warning("[TRANSLATION] Cache has unexpected format, ignoring")
                    return None
                return data
        except Exception as e:
            logger.error(f"[TRANSLATION] Failed to read cache: {e}")
            return None

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"[TRANSLATION] Cache saved: {path}")
        except Exception as e:
            logger.warning(f"[TRANSLATION] Could not save cache: {e}")

    def _translate_with_retry(self, text, retries=3, delay=2):
        for attempt in range(retries):
            try:
                result = self.translator.translate(text)
                if result is None:
                    raise ValueError("Empty response from translator")
                return result
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"[RETRY {attempt + 1}/{retries}] {e} — retrying in {delay}s")
                    time.sleep(delay)
                else:
                    logger.error(f"[TRANSLATION] Failed after {retries} attempts. Returning original.")
                    return text


if __name__ == "__main__":
    service = TranslationService()
    test_data = [{"start": 0.0, "end": 2.0, "text": "I love programming"}]
    result = service.translate_segments(test_data, "storage/test_cache.json")
    print(result)
