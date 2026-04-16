import os
import json
import logging
import time 
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

BATCH_SIZE = 150 

RETRY_DELAY = 2


class TranslationService:
    def __init__(self, source="en", target="he"):
        self.model = genai.GenerativeModel('gemma-3-12b-it')
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
        lines = "\n".join([f"{offset + i} ||| {seg['text']}" for i, seg in enumerate(batch)])
        prompt = f"""IMPORTANT: You are an expert subtitle translator. Your task is to translate to {lang_name} ONLY.

MANDATORY RULES:
1. Translate EVERY line into {lang_name}
2. Format MUST be: ID ||| Translated Text 
3. Do NOT include explanations, notes, code, or extra output
4. Do NOT respond in English - all output must be in {lang_name}
5. Keep timing and meaning intact
6. If line is already in {lang_name}, keep it as-is
7. ACCURACY: If the speaker mentions a specific language (e.g., 'Korean', 'English', 'Spanish'), translate the name of that language literally. Do NOT replace it with '{lang_name}'.

Text to translate to {lang_name}:
{lines}

Remember: Output ONLY the translated lines in {lang_name} format. Nothing else."""

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)

                if not response or not response.text:
                    logger.error(f"[GEMINI] Empty response for batch {offset}, attempt {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        time.sleep(RETRY_DELAY)
                    continue

                translated_dict = self._parse_translation_response(response.text, offset, len(batch))
                
                if not translated_dict:
                    logger.warning(f"[GEMINI] No valid translations parsed at batch {offset}")
                    if attempt < max_retries - 1:
                        time.sleep(RETRY_DELAY)
                    continue
                
                is_valid = self._validate_translation_language(translated_dict, lang_name, offset)
                
                if is_valid:
                    for i, seg in enumerate(batch):
                        global_idx = offset + i
                        if global_idx in translated_dict:
                            seg['text'] = translated_dict[global_idx]
                    logger.info(f"[GEMINI] Batch {offset}: {len(translated_dict)}/{len(batch)} → {lang_name}")
                    return
                else:
                    logger.warning(f"[GEMINI] Batch {offset}: Language validation FAILED - retrying...")
                    if attempt < max_retries - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        logger.error(f"[GEMINI] Batch {offset}: Failed validation after {max_retries} attempts")

            except Exception as e:
                logger.error(f"[GEMINI] Batch {offset} attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"[GEMINI] Batch {offset}: Giving up, keeping original text")
                else:
                    time.sleep(RETRY_DELAY)

    def _parse_translation_response(self, response_text: str, offset: int, batch_size: int) -> dict:
        translated_dict = {}
        for line in response_text.strip().split('\n'):
            line = line.strip()
            if not line or "|||" not in line:
                continue
            try:
                parts = line.split("|||", 1)
                if len(parts) != 2:
                    continue
                idx_str = parts[0].strip()
                text = parts[1].strip()
                
                try:
                    idx = int(idx_str)
                    if text:  
                        translated_dict[idx] = text
                except ValueError:
                    continue
            except Exception:
                continue
        return translated_dict

    def _validate_translation_language(self, translations: dict, target_lang: str, offset: int) -> bool:
        if not translations:
            return False
        
        sample_texts = list(translations.values())[:3]
        if not sample_texts:
            return False
        sample_text = " ".join(sample_texts).lower()
        
        strong_english = [' is ', ' are ', ' the ', ' and ', ' a ', ' to ', ' of ']
        english_count = sum(1 for eng in strong_english if eng in sample_text)
        
        if target_lang in ['he', 'iw']: 
            hebrew_chars = sum(1 for c in sample_text if '\u0590' <= c <= '\u05FF')
            total_chars = len(sample_text.replace(' ', ''))
            is_valid = hebrew_chars > total_chars * 0.35 and english_count < 2
            logger.info(f"[GEMINI] Validate {offset}: Hebrew={hebrew_chars}/{total_chars} ({(hebrew_chars/total_chars*100):.0f}%), en_score={english_count}, ✓={is_valid}")
            return is_valid
        elif target_lang in ['ar']:  
            arabic_chars = sum(1 for c in sample_text if '\u0600' <= c <= '\u06FF')
            total_chars = len(sample_text.replace(' ', ''))
            is_valid = arabic_chars > total_chars * 0.35 and english_count < 2
            return is_valid
        elif target_lang in ['en']: 
            return english_count > 0 or 'english' not in sample_text
        else: 
            return english_count < 2

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"[GEMINI] Cache saved: {path}")
        except Exception as e:
            logger.warning(f"[GEMINI] Could not save cache: {e}")
