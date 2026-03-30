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
from typing import Optional, Any
import os
import re
import time
import logging
import uuid
import threading
import asyncio
import traceback


STATUS_PENDING = "pending"
STATUS_DOWNLOADING = "downloading"
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSLATING = "translating"
STATUS_FINALIZING = "finalizing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

AUDIO_SOURCE_LANGUAGE = "en"

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
    target_language: str = "he"


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
    target_language: str = "he",
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
        args=(job_id, file_path, request_id, target_language, generate_summary, summary_sentences),
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
        video_res, audio_res = video_service.download_both(source, storage_manager=storage_manager)
        if audio_res.get("status") != "success":
            raise Exception(f"YouTube audio download failed: {audio_res.get('message', '')}")
        return video_id, audio_res["file_path"], video_res["file_path"]
    else:
        storage_manager.touch_file(source)
        return f"local_{job_id}", source, source


def process_video_job(job_id: str, source: str, request_id: str, target_lang: str, generate_summary: bool, summary_sentences: int):
    storage_manager.cleanup_if_needed()
    try:
        if job_manager.get_job(job_id)["status"] == STATUS_CANCELLED:
            return

        job_manager.update_status(job_id, STATUS_DOWNLOADING)
        job_manager.update_progress(job_id, 10)
        logger.info(f"[{request_id}] Preparing source: {source}")
        video_id, audio_path, video_display_url = prepare_source(source, job_id)
        paths = get_video_paths(video_id, lang=target_lang)
        logger.info(f"[{request_id}] Source ready. audio={audio_path}")

        job_manager.update_status(job_id, STATUS_TRANSCRIBING)
        job_manager.update_progress(job_id, 30)
        logger.info(f"[{request_id}] Starting transcription...")

        trans_res = transcription_service.transcribe(
            audio_path,
            paths["json"],
            language=AUDIO_SOURCE_LANGUAGE,
            storage_manager=storage_manager,
            job_id=job_id,
            job_manager=job_manager
        )

        if not trans_res.get("success"):
            raise Exception(f"Transcription failed: {trans_res.get('error', 'Unknown error')}")

        segments = trans_res["segments"]
        logger.info(f"[{request_id}] Transcription done. {len(segments)} segments.")

        if not segments:
            raise Exception("Transcription produced no segments")

        if job_manager.get_job(job_id)["status"] == STATUS_CANCELLED:
            return

        job_manager.update_status(job_id, STATUS_TRANSLATING)
        job_manager.update_progress(job_id, 60)
        logger.info(f"[{request_id}] Starting translation of {len(segments)} segments → {target_lang}...")

        translated_segments = translation_service.translate_segments(
            segments,
            paths["trans"],
            target_lang=target_lang,
            storage_manager=storage_manager
        )

        if not translated_segments:
            raise Exception("Translation returned empty result")

        logger.info(f"[{request_id}] Translation done. {len(translated_segments)} segments.")

        job_manager.update_status(job_id, STATUS_FINALIZING)
        job_manager.update_progress(job_id, 90)

        subtitle_service.generate_srt(translated_segments, paths["srt_lang"], storage_manager=storage_manager)

        summary_text = None
        if generate_summary:
            raw_text = summary_service.build_text(translated_segments)
            summary_text = summary_service.summarize(
                raw_text, paths["summary"],
                sentences_count=summary_sentences,
                storage_manager=storage_manager
            )

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
            logger.error(f"[{request_id}] Job {job_id} FAILED at status '{current_status}': {str(e)}")
            logger.error(traceback.format_exc())
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
        "eta_seconds": job.get("eta_seconds"),
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
