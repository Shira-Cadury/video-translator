import re
import os
import nltk
import time
import logging
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from app.config import STORAGE_PATH

logger = logging.getLogger(__name__)  


class SummaryService:

    def __init__(self):
        os.makedirs(os.path.join(STORAGE_PATH, "summaries"), exist_ok=True)
        self._init_nltk()

    def _init_nltk(self):
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')

    def build_text(self, segments):
        if not segments:
            return ""
        text = " ".join([segment.get("text", "") for segment in segments])
        return self.clean_text(text)

    def clean_text(self, text):
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def summarize(self, text, output_path=None, sentences_count=3, storage_manager=None):
        if not text:
            return "No text to summarize"
        
        if output_path and os.path.exists(output_path):
            logger.info(f"[CACHE] Summary found, updating access time: {output_path}")
            if storage_manager:
                storage_manager.touch_file(output_path)
            return self._load_cache(output_path)
        cleaned_text = self.clean_text(text)

        if not cleaned_text or len(cleaned_text) < 10:
            return "Text too short for summary"

        if len(cleaned_text) > 10000:
            cleaned_text = cleaned_text[:10000]

        logger.info(f"Summarizing ({len(cleaned_text)} chars)")
        start = time.time()

        summary = self._run_lsa_summarizer(cleaned_text, sentences_count)

        logger.info(f"[TIME] Summary: {time.time() - start:.2f}s")

        if summary and output_path:
            self._save_cache(summary, output_path)

        return summary or "Summary could not be generated"

    def _run_lsa_summarizer(self, text, count):
        try:
            parser = PlaintextParser.from_string(text, Tokenizer("english"))
            summarizer = LsaSummarizer()
            sentences = summarizer(parser.document, count)
            return "\n".join([f"• {str(s)}" for s in sentences])
        except Exception as e:
            logger.error(f"NLP Error: {e}")
            return None

    def _load_cache(self, path):
        if not path or not os.path.exists(path):
            return None
        try:
            logger.info(f"[CACHE] Loading summary from cache: {path}")
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            logger.warning("Summary cache corrupted, ignoring")
            return None

    def _save_cache(self, data, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
            logger.info(f"[SAVED] Summary saved: {path}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to save summary: {e}")
