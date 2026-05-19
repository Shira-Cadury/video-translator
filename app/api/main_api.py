import os
import re
import time
import logging
import uuid
import asyncio
import traceback
import subprocess
import nltk
import json
import hashlib
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, File, UploadFile, Request, Depends, Form
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
from app.services.translation_service import TranslationService
from app.services.summary_service import SummaryService
from app.services.job_manager import JobManager
from app.config import LOG_FILE, STORAGE_PATH, MAX_SUMMARY_SENTENCES, MODEL_SIZE
from app.services.video_source_service import VideoSourceService
from app.services.storage_manager import StorageManager
from app.services.queue_service import QueueService
from app.services.search_service import SearchService

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    logger.info("Downloading NLTK packages")
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)

security = HTTPBearer()

def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    correct_token = os.environ.get("ADMIN_TOKEN", "shira_super_secret_admin_token_2026")
    if credentials.credentials != correct_token:
        logger.warning(f"[SECURITY] Failed admin login attempt!")
        raise HTTPException(status_code=403, detail="Not authorized")
    return credentials.credentials

STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSLATING = "translating"
STATUS_FINALIZING = "finalizing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
AUDIO_SOURCE_LANGUAGE = "en"

os.makedirs(STORAGE_PATH, exist_ok=True)
video_service = VideoService()
transcription_service = TranscriptionService()
subtitle_service = SubtitleService()
translation_service = TranslationService()
summary_service = SummaryService()
job_manager = JobManager()
video_source_service = VideoSourceService(STORAGE_PATH)
storage_manager = StorageManager(STORAGE_PATH)
queue_service = QueueService()
search_service = SearchService(STORAGE_PATH)

def get_real_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

limiter = Limiter(key_func=get_real_ip)

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage_manager.cleanup_if_needed()
    yield
    queue_service.job_queue.join()

app = FastAPI(lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins_str = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
origins_list = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount(f"/{STORAGE_PATH}", StaticFiles(directory=STORAGE_PATH), name="storage")

class VideoRequest(BaseModel):
    url: str | None = None
    generate_summary: bool = True
    summary_sentences: int = Field(default=3, ge=1, le=MAX_SUMMARY_SENTENCES)
    target_language: str = "he"

def extract_video_id(url: str):
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if video_id_match:
        return video_id_match.group(1)
    return hashlib.md5(url.encode('utf-8')).hexdigest()[:15]

def prepare_source(source: str, job_id: str):
    if video_source_service.is_url(source):
        video_id = extract_video_id(source) or f"web_{job_id}"
        video_res, audio_res = video_service.download_both(source, storage_manager=storage_manager)
        if audio_res.get("status") != "success":
            raise Exception(f"Download failed: {audio_res.get('message', 'Link not supported')}")
        return video_id, audio_res["file_path"], video_res["file_path"]
    else:
        storage_manager.touch_file(source)
        return f"local_{job_id}", source, source

def get_video_paths(video_id: str, lang: str):
    return {
        "json": f"{STORAGE_PATH}/subtitles/{video_id}.json",
        "trans": f"{STORAGE_PATH}/subtitles/{video_id}_{lang}.json",
        "summary": f"{STORAGE_PATH}/subtitles/{video_id}_summary_{lang}.txt",
        "srt_lang": f"{STORAGE_PATH}/subtitles/{video_id}_{lang}.srt",
    }

def _burn_subtitles(video_path: str, srt_path: str, output_path: str) -> str:
    try:
        MAX_BURN_TIME = 600
        safe_srt_path = srt_path.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'").replace(',', '\\,')
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vf', f"subtitles={safe_srt_path}:force_style='FontSize=20,PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=1'",
            '-c:a', 'copy', output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=MAX_BURN_TIME)
        return output_path
    
    except Exception as e:
        logger.error(f"[FFMPEG] Error: {e}")
        raise e

def process_video_job(job_id: str, source: str, request_id: str, target_lang: str, generate_summary: bool, summary_sentences: int):
    storage_manager.cleanup_if_needed()
    job_overall_start = time.time()
    audio_path = None
    raw_video_path = None

    try:
        job_manager.update_status(job_id, STATUS_DOWNLOADING)
        job_manager.update_progress(job_id, 10)
        
        is_url = video_source_service.is_url(source)
        precalc_video_id = extract_video_id(source) if is_url else f"local_{job_id}"
        paths = get_video_paths(precalc_video_id, lang=target_lang)
        
        burned_video_path = f"{STORAGE_PATH}/subtitles/{precalc_video_id}_{target_lang}_final.mp4"
        
        if is_url and os.path.exists(burned_video_path) and os.path.exists(paths["srt_lang"]):
            logger.info(f"[{request_id}] CACHE HIT: Video already processed for language {target_lang}. Skipping everything!")
            summary_text = None
            if generate_summary and os.path.exists(paths["summary"]):
                with open(paths["summary"], "r", encoding="utf-8") as f:
                    summary_text = f.read()
            
            job_manager.update_progress(job_id, 100)
            job_manager.save_result(job_id, {
                "video_id": precalc_video_id,
                "video_url": burned_video_path,
                "subtitles": paths["srt_lang"],
                "summary": summary_text
            })
            job_manager.update_status(job_id, STATUS_COMPLETED)
            return 

        video_id, audio_path, raw_video_path = prepare_source(source, job_id)
        job_manager.update_progress(job_id, 30)
        
        paths = get_video_paths(video_id, lang=target_lang)
        
        burned_video_path = f"{STORAGE_PATH}/subtitles/{video_id}_{target_lang}_final.mp4"

        job_manager.update_status(job_id, STATUS_TRANSCRIBING)
        trans_res = transcription_service.transcribe(
            audio_path, paths["json"],
            language=AUDIO_SOURCE_LANGUAGE,
            storage_manager=storage_manager,
            job_id=job_id, job_manager=job_manager
        )
        job_manager.update_progress(job_id, 60)

        if not trans_res.get("success"):
            raise Exception(f"Transcription failed: {trans_res.get('error')}")

        job_manager.update_status(job_id, STATUS_TRANSLATING)
        translated_segments = translation_service.translate_segments(
            trans_res["segments"], paths["trans"],
            target_lang=target_lang,
            storage_manager=storage_manager
        )
        
        try:
            logger.info(f"[{request_id}] Building search index")
            search_service.build_index(job_id, translated_segments)
        except Exception as e:
            logger.warning(f"[{request_id}] Search index failed, continuing anyway: {e}")    
        
        job_manager.update_progress(job_id, 80)

        job_manager.update_status(job_id, STATUS_FINALIZING)
        subtitle_service.generate_srt(translated_segments, paths["srt_lang"], storage_manager=storage_manager)
        
        job_manager.update_status(job_id, "burning_subtitles")
        if not os.path.exists(burned_video_path):
            logger.info(f"[{request_id}] Burning subtitles to new video...")
            _burn_subtitles(raw_video_path, paths["srt_lang"], burned_video_path)
        else:
            logger.info(f"[{request_id}] Using cached burned video. Skipping FFmpeg.")
        job_manager.update_progress(job_id, 95)
        
        summary_text = None
        if generate_summary:
            raw_text = summary_service.build_text(translated_segments)
            summary_text = summary_service.summarize(raw_text, paths["summary"], sentences_count=summary_sentences, storage_manager=storage_manager)

        job_manager.update_progress(job_id, 100)
        job_manager.save_result(job_id, {
            "video_id": video_id,
            "video_url": burned_video_path,
            "subtitles": paths["srt_lang"],
            "summary": summary_text
        })
        job_manager.update_status(job_id, STATUS_COMPLETED)
        logger.info(f"[{request_id}] == JOB COMPLETED == {time.time() - job_overall_start:.1f}s")

    except Exception as e:
        logger.error(f"Job {job_id} FAILED: {str(e)}")
        traceback.print_exc()
        job_manager.fail_job(job_id, {"error": str(e)})
    finally:
        for temp_file in [audio_path, raw_video_path]:
            if temp_file and os.path.exists(temp_file):
                try: 
                    os.remove(temp_file)
                except: 
                    pass

@app.post("/upload-video")
@limiter.limit("5/minute")
async def upload_video(
    request: Request, 
    file: UploadFile = File(...),
    target_language: str = Form("he"),
    generate_summary: bool = Form(True),
    summary_sentences: int = Form(3)
):
    safe_filename = os.path.basename(file.filename).replace(" ", "_")
    file_path = await asyncio.to_thread(video_source_service.save_uploaded_file, file)
    request_id = str(uuid.uuid4())[:8]
    job_id = job_manager.create_job()
    job_manager.update_status(job_id, STATUS_QUEUED)
    queue_service.add_job(process_video_job, job_id, file_path, request_id, target_language, generate_summary, summary_sentences)
    return {"status": STATUS_QUEUED, "job_id": job_id}

@app.post("/process-video")
@limiter.limit("5/minute")
def process_video(request: Request, body: VideoRequest): 
    if not body.url:
        raise HTTPException(status_code=400, detail="URL field is required.")
    
    parsed_url = urlparse(body.url)
    if parsed_url.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    request_id = str(uuid.uuid4())[:8]
    job_id = job_manager.create_job()
    job_manager.update_status(job_id, STATUS_QUEUED)
    queue_service.add_job(process_video_job, job_id, body.url, request_id, body.target_language, body.generate_summary, body.summary_sentences)
    return {"status": STATUS_QUEUED, "job_id": job_id}

@app.get("/status/{job_id}")
def check_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job: 
        raise HTTPException(status_code=404, detail="Job ID not found")
    return job

@app.get("/stream-status/{job_id}")
async def stream_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    
    async def event_generator():
        last_progress = -1
        last_status = ""
        while True:
            current_job = job_manager.get_job(job_id)
            if not current_job: break
            if current_job["progress"] != last_progress or current_job["status"] != last_status:
                last_progress = current_job.get("progress", 0)
                last_status = current_job["status"]
                yield f"data: {json.dumps(current_job)}\n\n"
            if last_status in [STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED]:
                break
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/health")
@limiter.limit("30/minute") 
def health(request: Request): 
    return {"status": "ok", "timestamp": time.time(), "transcription": "ready"}

@app.get("/jobs", dependencies=[Depends(verify_admin)])
def list_all_jobs():
    return job_manager.jobs

@app.get("/stats", dependencies=[Depends(verify_admin)])
def get_stats():
    return {
        "status": "online",
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active_jobs": len(job_manager.jobs)
    }

@app.post("/cancel/{job_id}")
def cancel_video_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    job_manager.cancel_job(job_id)
    return {"status": "cancelled"}

@app.get("/queue-status")
def get_queue_info():
    return {"queue_size": queue_service.get_queue_size(), "status": "active"}

@app.get("/search/{job_id}")
@limiter.limit("30/minute")
def search_video_text(request: Request, job_id: str, q: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    
    if not q or len(q.strip()) == 0:
        raise HTTPException(status_code=400, detail="Query is required")
    
    try:
        result = search_service.search(job_id, q)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[SEARCH] Error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")