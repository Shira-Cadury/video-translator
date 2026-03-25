from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles 
from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
from app.services.translation_service import TranslationService
from app.services.summary_service import SummaryService
from app.services.job_manager import JobManager
import os
import re
import time
import logging
import uuid
import threading


STATUS_PENDING = "pending"
STATUS_DOWNLOADING = "downloading"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSLATING = "translating"
STATUS_FINALIZING = "finalizing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

video_service = VideoService()
transcription_service = TranscriptionService()
subtitle_service = SubtitleService()
translation_service = TranslationService()
summary_service = SummaryService()
job_manager = JobManager()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

os.makedirs("storage", exist_ok=True)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

class VideoRequest(BaseModel):
    url: str
    generate_summary: bool = True
    summary_sentences: int = Field(default=3, ge=1, le=10)
    target_language: str = "he" 
    
def cleanup_old_files(folder_path, max_age_hours=24):
    if not os.path.exists(folder_path):
        return
    
    now = time.time()
    count = 0
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            file_age = now - os.path.getmtime(file_path)
            if file_age > (max_age_hours * 3600):
                os.remove(file_path)
                count += 1
    if count > 0:
        logger.info(f"[CLEANUP] Deleted {count} old files from {folder_path}")                

def extract_video_id(url: str):
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not video_id_match:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format")
    return video_id_match.group(1)

def get_video_paths(video_id: str, lang: str):
    return {
        "json": f"storage/subtitles/{video_id}.json",
        "trans": f"storage/subtitles/{video_id}_{lang}.json",
        "summary": f"storage/subtitles/{video_id}_summary_{lang}.txt",
        "srt_en": f"storage/subtitles/{video_id}.srt",
        "srt_lang": f"storage/subtitles/{video_id}_{lang}.srt",
        "vtt_lang": f"storage/subtitles/{video_id}_{lang}.vtt"
    }
    
    

def process_video_job(job_id: str, url: str, request_id: str, target_lang: str, generate_summary: bool, summary_sentences: int):
    try:
        video_id = extract_video_id(url)
        paths = get_video_paths(video_id, lang=target_lang)
        
        job_manager.update_status(job_id, STATUS_DOWNLOADING)
        video_res = video_service.download_video(url)
        
        audio_path = video_service.download_audio(url)["file_path"]
        
        job_manager.update_status(job_id, STATUS_TRANSCRIBING)
        trans_res = transcription_service.transcribe(audio_path, paths["json"])
        segments = trans_res["segments"]
        
        job_manager.update_status(job_id, STATUS_TRANSLATING)
        translated_segments = translation_service.translate_segments(segments, paths["trans"], target_lang=target_lang)
        
        job_manager.update_status(job_id, STATUS_FINALIZING)
        subtitle_service.generate_srt(translated_segments, paths["srt_lang"])
        
        summary_text = None
        if generate_summary:
            raw_text = summary_service.build_text(translated_segments)
            summary_text = summary_service.summarize(raw_text, paths["summary"], sentences_count=summary_sentences)
            
        result_data = {
            "video_id": video_id,
            "video_url": video_res['file_path'],
            "subtitles": paths["srt_lang"],
            "summary": summary_text
        }    
        job_manager.save_result(job_id, result_data)
        logger.info(f"[{request_id}] Job {job_id} completed successfully!")
    except Exception as e:
        logger.error(f"[{request_id}] Job {job_id} failed: {str(e)}")
        job_manager.update_status(job_id, STATUS_FAILED)
        job_manager.save_result(job_id, {"error": str(e)})     
    
    
@app.on_event("startup")
async def startup_event():
    logger.info("--- Server starting up... Running Cleanup ---")
    cleanup_old_files("storage/video")
    cleanup_old_files("storage/audio")
    cleanup_old_files("storage/subtitles")
    
    
@app.get("/files")
def list_files():
    return{
        "videos": os.listdir("storage/video") if os.path.exists("storage/video") else [],
        "audio": os.listdir("storage/audio") if os.path.exists("storage/audio") else [],
        "subtitles": os.listdir("storage/subtitles") if os.path.exists("storage/subtitles") else []
    }
    
    
@app.get("/stats")
def get_stats():
    def count_files(directory):
        if os.path.exists(directory):
            return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])
        return 0
    
    return{
        "status": "online",
        "storage_summary": {
            "videos": count_files("storage/video"),
            "audio_files": count_files("storage/audio"),
            "subtitles_json": count_files("storage/subtitles"),
        },
        "system_info": {
            "log_file_exists": os.path.exists("app.log"),
            "server_time": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    }   
    
    
@app.get("/status/{job_id}")
def check_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    response = {
        "status": job["status"],
        "created_at": job["created_at"]
    }   
    
    if job.get("result"):
        response["result"] = job["result"]
        
    return response    
    
    
@app.post("/process-video")
def process_video(request: VideoRequest):
    request_id = str(uuid.uuid4())[:8]
    job_id = job_manager.create_job()
    logger.info(f"Received request for URL: {request.url}. Created Job ID: {job_id}")
    
    thread = threading.Thread(
        target=process_video_job,
        args=(
            job_id,
            request.url,
            request_id,
            request.target_language,
            request.generate_summary,
            request.summary_sentences
        ),
        daemon=True
    )
    thread.start()
    
    return{
        "status": "processing",
        "job_id": job_id,
        "message": "Processing started in background. Check status at /status/{job_id}"
    }