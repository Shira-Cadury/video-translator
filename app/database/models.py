import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database.db_config import Base

class Video(Base):
    __tablename__ = "videos"
    id = Column(String, primary_key=True, index=True)
    source_type = Column(String, nullable=False)
    original_url = Column(String, nullable=True)
    original_language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    jobs = relationship("Job", back_populates="video", cascade="all, delete-orphan")
    segments = relationship("SubtitleSegment", back_populates="video", cascade="all, delete-orphan")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, index=True)
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    target_language = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    progress = Column(Integer, default=0)
    burned_video_path = Column(String, nullable=True)
    srt_path = Column(String, nullable=True)
    summary_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    video = relationship("Video", back_populates="jobs")
    segments = relationship("SubtitleSegment", back_populates="job", cascade="all, delete-orphan")

class SubtitleSegment(Base):
    __tablename__ = "subtitle_segments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    segment_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    video = relationship("Video", back_populates="segments")
    job = relationship("Job", back_populates="segments")