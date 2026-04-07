import os
import json
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

LANGUAGE_NAMES = {
    "he": "Hebrew",
    "iw": "Hebrew",
    "en": "English",
    "ar": "Arabic",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "tr": "Turkish",
    "pt": "Portuguese",
    "it": "Italian",
}

BATCH_SIZE = 80  


class TranslationService:
    def __init__(self, source="en", target="he"):
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.default_target = target

    def translate_segments(self, segments, output_path=None, target_lang="he", storage_manager=None):
        if not segments:
            return []

        
        lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
        logger.info(f"[GEMINI] Target language: '{target_lang}' → '{lang_name}'")

        if output_path and os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    if isinstance(cached, list) and cached:
                        logger.info(f"[GEMINI] Loaded translation from cache: {output_path}")
                        if storage_manager:
                            storage_manager.touch_file(output_path)
                        return cached
            except Exception as e:
                logger.warning(f"[GEMINI] Cache read failed: {e}, re-translating...")

        logger.info(f"[GEMINI] Translating {len(segments)} segments → {lang_name}...")

        translated_segments = [dict(seg) for seg in segments]

        for batch_start in range(0, len(translated_segments), BATCH_SIZE):
            batch = translated_segments[batch_start: batch_start + BATCH_SIZE]
            self._translate_batch(batch, lang_name, batch_start)

        logger.info(f"[GEMINI] Translation complete. {len(translated_segments)} segments.")

        if output_path:
            self._save_cache(translated_segments, output_path)

        return translated_segments

    def _translate_batch(self, batch: list, lang_name: str, offset: int):
        """Translate a batch of segments in one Gemini call."""
        lines = "\n".join([f"{offset + i} ||| {seg['text']}" for i, seg in enumerate(batch)])

        prompt = f"""You are a professional subtitle translator.
Translate each line below into natural, modern {lang_name}.
Keep the exact format: ID ||| Translated Text
Do NOT add explanations, notes, or extra lines.
Translate EVERY line — do not skip any.

{lines}"""

        try:
            response = self.model.generate_content(prompt)

            if not response or not response.text:
                logger.error(f"[GEMINI] Empty response for batch at offset {offset}")
                return 

            translated_dict = {}
            for line in response.text.strip().split('\n'):
                if "|||" not in line:
                    continue
                parts = line.split("|||", 1)
                try:
                    idx = int(parts[0].strip())
                    text = parts[1].strip()
                    translated_dict[idx] = text
                except (ValueError, IndexError):
                    continue

            for i, seg in enumerate(batch):
                global_idx = offset + i
                if global_idx in translated_dict:
                    seg['text'] = translated_dict[global_idx]
                else:
                    logger.warning(f"[GEMINI] Missing translation for segment {global_idx}, keeping original")

            logger.info(f"[GEMINI] Batch offset {offset}: translated {len(translated_dict)}/{len(batch)} segments")

        except Exception as e:
            logger.error(f"[GEMINI] Batch translation failed at offset {offset}: {e}")

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"[GEMINI] Cache saved: {path}")
        except Exception as e:
            logger.warning(f"[GEMINI] Could not save cache: {e}")
