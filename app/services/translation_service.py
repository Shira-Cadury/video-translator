import os
import json
import time
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = "AIzaSyALxR22KG0xxNpBJ2-O37A9dtCu2UTI1fw" 
genai.configure(api_key=GEMINI_API_KEY)

class TranslationService:
    def __init__(self, source="en", target="he"):
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.target_lang = "Hebrew"

    def translate_segments(self, segments, output_path=None, target_lang="he", storage_manager=None):
        if not segments:
            return []

        if output_path and os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass

        logger.info(f"[GEMINI] Translating {len(segments)} segments...")

        full_text_to_translate = "\n".join([f"{i} ||| {seg['text']}" for i, seg in enumerate(segments)])
        
        prompt = f"""
        You are a professional video subtitle translator. 
        Translate the following segments into natural, modern {self.target_lang}.
        Context: This is a video about the K-pop group Stray Kids.
        IMPORTANT: Maintain the format 'ID ||| Translated Text' for each line.
        
        Original Text:
        {full_text_to_translate}
        """

        try:
            response = self.model.generate_content(prompt)
            translated_lines = response.text.strip().split('\n')
            
            translated_dict = {}
            for line in translated_lines:
                if "|||" in line:
                    parts = line.split("|||")
                    try:
                        idx = int(parts[0].strip())
                        text = parts[1].strip()
                        translated_dict[idx] = text
                    except: continue

            for i, seg in enumerate(segments):
                if i in translated_dict:
                    seg['text'] = translated_dict[i]
            
            if output_path:
                self._save_cache(segments, output_path)
                
            return segments

        except Exception as e:
            logger.error(f"[GEMINI] Error: {e}")
            return segments 

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except: pass