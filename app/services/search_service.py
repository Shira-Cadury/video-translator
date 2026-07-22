import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import models

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def build_index(self, job_id: str, segments: list):
        pass

    def search(self, db: Session, job_id: str, query: str) -> dict:
        query_clean = query.strip()
        if not query_clean:
            return {"query": query, "total_matches": 0, "matches": []}

        results = db.query(models.SubtitleSegment).filter(
            models.SubtitleSegment.job_id == job_id,
            or_(
                models.SubtitleSegment.source_text.contains(query_clean),
                models.SubtitleSegment.translated_text.contains(query_clean)
            )
        ).order_by(models.SubtitleSegment.segment_index).all()

        matches = []
        for seg in results:
            text_context = seg.translated_text if query_clean in seg.translated_text else seg.source_text
            
            matches.append({
                "time": round(seg.start_time, 2),
                "context": self._extract_context(text_context, query_clean)
            })

        logger.info(f"[SEARCH DB] Found {len(matches)} matches for query '{query_clean}' in job {job_id}")

        return {
            "query": query,
            "total_matches": len(matches),
            "matches": matches
        }

    def _extract_context(self, text: str, query: str, context_chars: int = 40) -> str:
        pos = text.lower().find(query.lower())
        if pos == -1: 
            return text[:50] + "..." if len(text) > 50 else text
        
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(query) + context_chars)
        context = text[start:end]
        
        if start > 0: 
            context = "..." + context
        if end < len(text): 
            context = context + "..."
        return context