from sqlalchemy.orm import Session
from app.database import models

def get_video(db: Session, video_id: str):
    return db.query(models.Video).filter(models.Video.id == video_id).first()

def create_video(db: Session, video_id: str, source_type: str, original_url: str = None, original_language: str = "en"):
    db_video = get_video(db, video_id)
    if db_video:
        return db_video
    
    db_video = models.Video(
        id=video_id,
        source_type=source_type,
        original_url=original_url,
        original_language=original_language
    )
    db.add(db_video)
    db.commit()
    db.refresh(db_video)
    return db_video

def get_job(db: Session, job_id: str):
    return db.query(models.Job).filter(models.Job.id == job_id).first()

def create_job(db: Session, job_id: str, video_id: str, target_language: str):
    db_job = models.Job(
        id=job_id,
        video_id=video_id,
        target_language=target_language,
        status="pending",
        progress=0
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

def update_job_progress(db: Session, job_id: str, progress: int, status: str = None):
    db_job = get_job(db, job_id)
    if db_job:
        db_job.progress = progress
        if status:
            db_job.status = status
        db.commit()
        db.refresh(db_job)
    return db_job

def complete_job(db: Session, job_id: str, burned_path: str, srt_path: str, summary_text: str = None):
    db_job = get_job(db, job_id)
    if db_job:
        db_job.status = "completed"
        db_job.progress = 100
        db_job.burned_video_path = burned_path
        db_job.srt_path = srt_path
        db_job.summary_text = summary_text
        db.commit()
        db.refresh(db_job)
    return db_job

def create_subtitle_segments(db: Session, video_id: str, job_id: str, segments_list: list):
    db_segments = []
    for idx, seg in enumerate(segments_list):
        db_seg = models.SubtitleSegment(
            video_id=video_id,
            job_id=job_id,
            segment_index=idx,
            start_time=float(seg.get("start", 0.0)),
            end_time=float(seg.get("end", 0.0)),
            source_text=seg.get("source_text", ""),
            translated_text=seg.get("translated_text", "")
        )
        db_segments.append(db_seg)
        db.bulk_save_objects(db_segments)
        db.commit()