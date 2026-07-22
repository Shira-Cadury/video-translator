import logging
from sqlalchemy.orm import Session
from app.database import crud

logger = logging.getLogger(__name__)

class JobManager:
    def __init__(self):
        pass
    
    def create_job(self, db: Session, job_id: str, video_id: str, target_language: str):
        crud.create_job(db, job_id=job_id, video_id=video_id, target_language=target_language)
        logger.info(f"[JOB CREATED IN DB] {job_id} for video {video_id}")
        return job_id
    
    def update_progress(self, db: Session, job_id: str, progress: int):
        crud.update_job_progress(db, job_id=job_id, progress=progress)
        
    def update_status(self, db: Session, job_id: str, status: str):
        job = crud.get_job(db, job_id)
        current_progress = job.progress if job else 0
        crud.update_job_progress(db, job_id=job_id, progress=current_progress, status=status)
        logger.info(f"[JOB STATUS UPDATED] {job_id} -> {status}")
        
    def cancel_job(self, db: Session, job_id: str):
        self.update_status(db, job_id, "cancelled") 
        
    def save_result(self, db: Session, job_id: str, burned_path: str, srt_path: str, summary_text: str = None):
        crud.complete_job(db, job_id=job_id, burned_path=burned_path, srt_path=srt_path, summary_text=summary_text)
        logger.info(f"[JOB COMPLETED] {job_id} saved to DB cache")
        
    def fail_job(self, db: Session, job_id: str, error_message: str = None):
        job = crud.get_job(db, job_id)
        current_progress = job.progress if job else 0
        crud.update_job_progress(db, job_id=job_id, progress=current_progress, status="failed")
        logger.error(f"[JOB FAILED] {job_id}. Reason: {error_message}")   
        
    def get_job(self, db: Session, job_id: str):
        job = crud.get_job(db, job_id)
        if not job:
            return None
        return {
            "id": job.id,
            "video_id": job.video_id,
            "status": job.status,
            "progress": job.progress,
            "burned_video_path": job.burned_video_path,
            "srt_path": job.srt_path,
            "summary_text": job.summary_text,
            "eta_seconds": getattr(job, "eta_seconds", None) 
        }
        
    def update_eta(self, db: Session, job_id: str, eta_seconds: int):    
        job = crud.get_job(db, job_id)
        if job:               
            job.eta_seconds = eta_seconds