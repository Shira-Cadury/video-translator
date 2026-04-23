import os
import re
import json
import logging
from typing import List

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.stop_words = {
            "את", "של", "על", "הוא", "היא", "זה", "עם", "כל", "גם", "מה", "אם", "לא", "כן",
            "the", "a", "an", "in", "on", "at", "to", "for", "is", "are", "and"
        }

    def _get_index_path(self, job_id: str) -> str:
        return os.path.join(self.storage_path, "subtitles", f"{job_id}_index.json")

    def build_index(self, job_id: str, segments: List[dict]):
        word_index = {}
        
        for seg in segments:
            text = seg.get("text", "")
            start_time = seg.get("start", 0)
            
            words = re.findall(r"\b[\w']+\b", text.lower())
            
            for word in words:
                if len(word) < 2 or word in self.stop_words:
                    continue
                
                if word not in word_index:
                    word_index[word] = []
                
                word_index[word].append({
                    "time": round(start_time, 2),
                    "context": self._extract_context(text, word)
                })
        
        index_path = self._get_index_path(job_id)
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(word_index, f, ensure_ascii=False)
            
        logger.info(f"[SEARCH] Index saved for {job_id} ({len(word_index)} unique words)")

    def search(self, job_id: str, query: str) -> dict:
        index_path = self._get_index_path(job_id)
        if not os.path.exists(index_path):
            raise ValueError("Search index not found for this video")
        
        with open(index_path, "r", encoding="utf-8") as f:
            word_index = json.load(f)
        
        query_clean = query.lower().strip()
        matches = word_index.get(query_clean, [])
        
        return {
            "query": query,
            "total_matches": len(matches),
            "matches": matches
        }

    def _extract_context(self, text: str, query: str, context_chars: int = 40) -> str:
        pos = text.lower().find(query)
        if pos == -1: return text[:50]
        
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(query) + context_chars)
        context = text[start:end]
        
        if start > 0: context = "..." + context
        if end < len(text): context = context + "..."
        return context