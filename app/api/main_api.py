from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
from app.services.translation_service import TranslationService
from app.services.summary_service import SummaryService
from app.services.job_manager import JobManager
from app.config import LOG_FILE, STORAGE_PATH, MAX_SUMMARY_SENTENCES
from app.services.video_source_service import VideoSourceService
from app.services.storage_manager import StorageManager
import os
import re
import time
import logging
import uuid
import threading
import asyncio


STATUS_PENDING = "pending"
STATUS_DOWNLOADING = "downloading"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSLATING = "translating"
STATUS_FINALIZING = "finalizing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

os.makedirs(STORAGE_PATH, exist_ok=True)

video_service = VideoService()
transcription_service = TranscriptionService()
subtitle_service = SubtitleService()
translation_service = TranslationService()
summary_service = SummaryService()
job_manager = JobManager()
video_source_service = VideoSourceService(STORAGE_PATH)
storage_manager = StorageManager(STORAGE_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- Server starting up... Running Cleanup ---")
    storage_manager.cleanup_if_needed()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(f"/{STORAGE_PATH}", StaticFiles(directory=STORAGE_PATH), name="storage")


class VideoRequest(BaseModel):
    url: str | None = None
    generate_summary: bool = True
    summary_sentences: int = Field(default=3, ge=1, le=MAX_SUMMARY_SENTENCES)
    target_language: str = "iw"


def extract_video_id(url: str):
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not video_id_match:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format")
    return video_id_match.group(1)


def get_video_paths(video_id: str, lang: str):
    return {
        "json": f"{STORAGE_PATH}/subtitles/{video_id}.json",
        "trans": f"{STORAGE_PATH}/subtitles/{video_id}_{lang}.json",
        "summary": f"{STORAGE_PATH}/subtitles/{video_id}_summary_{lang}.txt",
        "srt_lang": f"{STORAGE_PATH}/subtitles/{video_id}_{lang}.srt",
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


@app.post("/upload-video")
async def upload_video(
    file: UploadFile = File(...),
    target_language: str = "iw",
    generate_summary: bool = True,
    summary_sentences: int = 3
):
    storage_manager.cleanup_if_needed()

    file_path = await asyncio.to_thread(video_source_service.save_uploaded_file, file)

    request_id = str(uuid.uuid4())[:8]
    job_id = job_manager.create_job()
    logger.info(f"File uploaded. Starting job: {job_id}")

    thread = threading.Thread(
        target=process_video_job,
        args=(
            job_id,
            file_path,
            request_id,
            target_language,
            generate_summary,
            summary_sentences  
        ),
        daemon=True
    )
    thread.start()

    return {
        "status": "processing",
        "job_id": job_id,
        "message": "Upload complete. Processing started."
    }


@app.post("/cancel/{job_id}")
def cancel_video_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")

    if job["status"] in [STATUS_COMPLETED, STATUS_FAILED]:
        return {"message": "Job already finished."}

    job_manager.cancel_job(job_id)
    return {"status": "cancelled", "message": f"Job {job_id} was marked for cancellation."}


def prepare_source(source: str, job_id: str):
    if video_source_service.is_url(source):
        video_id = extract_video_id(source)

        video_res = video_service.download_video(source)
        audio_res = video_service.download_audio(source)

        if audio_res.get("status") != "success":
            raise Exception("YouTube audio download failed")

        storage_manager.touch_file(video_res["file_path"])
        storage_manager.touch_file(audio_res["file_path"])

        return video_id, audio_res["file_path"], video_res["file_path"]

    else:
        video_id = f"local_{job_id}"
        audio_path = source
        video_url = source

        storage_manager.touch_file(source)

        return video_id, audio_path, video_url


def process_video_job(job_id: str, source: str, request_id: str, target_lang: str, generate_summary: bool, summary_sentences: int):
    storage_manager.cleanup_if_needed()
    try:
        if job_manager.get_job(job_id)["status"] == STATUS_CANCELLED:
            return

        job_manager.update_status(job_id, STATUS_DOWNLOADING)
        job_manager.update_progress(job_id, 10)

        video_id, audio_path, video_display_url = prepare_source(source, job_id)
        paths = get_video_paths(video_id, lang=target_lang)

        job_manager.update_status(job_id, STATUS_TRANSCRIBING)
        job_manager.update_progress(job_id, 30)

        trans_res = transcription_service.transcribe(audio_path, paths["json"])
        if not trans_res.get("success"):
            raise Exception(f"Transcription failed: {trans_res.get('error', 'Unknown error')}")

        segments = trans_res["segments"]

        if job_manager.get_job(job_id)["status"] == STATUS_CANCELLED:
            return

        job_manager.update_status(job_id, STATUS_TRANSLATING)
        job_manager.update_progress(job_id, 60)
        translated_segments = translation_service.translate_segments(segments, paths["trans"], target_lang=target_lang)

        job_manager.update_status(job_id, STATUS_FINALIZING)
        job_manager.update_progress(job_id, 90)

        subtitle_service.generate_srt(translated_segments, paths["srt_lang"])

        summary_text = None
        if generate_summary:
            raw_text = summary_service.build_text(translated_segments)
            summary_text = summary_service.summarize(raw_text, paths["summary"], sentences_count=summary_sentences)

        result_data = {
            "video_id": video_id,
            "video_url": video_display_url,
            "subtitles": paths["srt_lang"],
            "summary": summary_text
        }

        job_manager.update_progress(job_id, 100)
        job_manager.save_result(job_id, result_data)
        logger.info(f"[{request_id}] Job {job_id} completed successfully!")

    except Exception as e:
        current_status = job_manager.get_job(job_id)["status"]
        if current_status != STATUS_CANCELLED:
            logger.error(f"[{request_id}] Job {job_id} failed: {str(e)}")
            job_manager.fail_job(job_id, {"error": str(e)})   


@app.get("/files")
def list_files():
    return {
        "videos": os.listdir(f"{STORAGE_PATH}/video") if os.path.exists(f"{STORAGE_PATH}/video") else [],
        "audio": os.listdir(f"{STORAGE_PATH}/audio") if os.path.exists(f"{STORAGE_PATH}/audio") else [],
        "subtitles": os.listdir(f"{STORAGE_PATH}/subtitles") if os.path.exists(f"{STORAGE_PATH}/subtitles") else []
    }


@app.get("/jobs")
def list_all_jobs():
    return job_manager.jobs


@app.get("/stats")
def get_stats():
    def count_files(directory):
        if os.path.exists(directory):
            return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])
        return 0

    return {
        "status": "online",
        "storage_summary": {
            "videos": count_files(f"{STORAGE_PATH}/video"),
            "audio_files": count_files(f"{STORAGE_PATH}/audio"),
            "subtitles_json": count_files(f"{STORAGE_PATH}/subtitles"),
        },
        "system_info": {
            "log_file_exists": os.path.exists(LOG_FILE),
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
        "progress": job.get("progress", 0),
        "created_at": job["created_at"]
    }

    if job.get("result"):
        response["result"] = job["result"]

    return response


@app.post("/process-video")
def process_video(request: VideoRequest):
    storage_manager.cleanup_if_needed()
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

    return {
        "status": "processing",
        "job_id": job_id,
        "message": "Processing started in background. Check status at /status/{job_id}"
    }
