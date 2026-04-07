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
from app.config import LOG_FILE, STORAGE_PATH, MAX_SUMMARY_SENTENCES, MODEL_SIZE
from app.services.video_source_service import VideoSourceService
from app.services.storage_manager import StorageManager
from app.services.queue_service import QueueService
import os
import re
import time
import logging
import uuid
import asyncio
import traceback
import subprocess


import nltk
nltk.download('punkt')
nltk.download('punkt_tab')


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
queue_service = QueueService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- Server starting up... Running Cleanup ---")
    storage_manager.cleanup_if_needed()
    yield
    queue_service.job_queue.join()

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
    if video_id_match:
        return video_id_match.group(1)
    return None


def prepare_source(source: str, job_id: str):
    if video_source_service.is_url(source):
        video_id = extract_video_id(source) or f"web_{job_id}"
        video_res, audio_res = video_service.download_both(source, storage_manager=storage_manager)
        if audio_res.get("status") != "success":
            raise Exception(f"Download failed: {audio_res.get('message', 'Link not supported or broken')}")
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
    """Burn subtitles into video using ffmpeg. Returns output path on success, original on failure."""
    try:
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vf', f"subtitles={srt_path}:force_style='FontSize=20,PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=1'",
            '-c:a', 'copy', output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"[FFMPEG] Subtitles burned into: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"[FFMPEG] Subtitle burn failed: {e.stderr.decode()}")
        return video_path  
    except Exception as e:
        logger.error(f"[FFMPEG] Unexpected error: {e}")
        return video_path


def process_video_job(job_id: str, source: str, request_id: str, target_lang: str, generate_summary: bool, summary_sentences: int):
    MAX_JOB_TIME = 7200
    storage_manager.cleanup_if_needed()
    job_overall_start = time.time()

    try:
        if job_manager.get_job(job_id)["status"] == STATUS_CANCELLED:
            return

        job_manager.update_status(job_id, STATUS_DOWNLOADING)
        job_manager.update_progress(job_id, 10)
        logger.info(f"[{request_id}] Preparing source: {source}")

        video_id, audio_path, raw_video_path = prepare_source(source, job_id)

        if time.time() - job_overall_start > MAX_JOB_TIME:
            raise Exception("Global timeout reached during download")

        paths = get_video_paths(video_id, lang=target_lang)
        burned_video_path = f"{STORAGE_PATH}/subtitles/{video_id}_final.mp4"
        logger.info(f"[{request_id}] Source ready. audio={audio_path}")

        job_manager.update_status(job_id, STATUS_TRANSCRIBING)
        job_manager.update_progress(job_id, 30)
        logger.info(f"[{request_id}] Starting transcription...")

        trans_res = transcription_service.transcribe(
            audio_path, paths["json"],
            language=AUDIO_SOURCE_LANGUAGE,
            storage_manager=storage_manager,
            job_id=job_id, job_manager=job_manager
        )

        if not trans_res.get("success"):
            raise Exception(f"Transcription failed: {trans_res.get('error')}")

        segments = trans_res["segments"]
        logger.info(f"[{request_id}] Transcription done. {len(segments)} segments.")

        if not segments:
            raise Exception("Transcription produced no segments")

        if time.time() - job_overall_start > MAX_JOB_TIME:
            raise Exception("Global timeout reached during transcription")

        job_manager.update_status(job_id, STATUS_TRANSLATING)
        job_manager.update_progress(job_id, 60)
        logger.info(f"[{request_id}] Starting translation → {target_lang}...")

        translated_segments = translation_service.translate_segments(
            segments, paths["trans"],
            target_lang=target_lang,
            storage_manager=storage_manager
        )

        if not translated_segments:
            logger.warning(f"[{request_id}] Translation returned empty — using original segments")
            translated_segments = segments

        logger.info(f"[{request_id}] Translation done. {len(translated_segments)} segments.")

        if time.time() - job_overall_start > MAX_JOB_TIME:
            raise Exception("Global timeout reached during translation")

        job_manager.update_status(job_id, STATUS_FINALIZING)
        job_manager.update_progress(job_id, 90)

        subtitle_service.generate_srt(translated_segments, paths["srt_lang"], storage_manager=storage_manager)

        job_manager.update_status(job_id, "burning_subtitles")
        final_video_url = _burn_subtitles(raw_video_path, paths["srt_lang"], burned_video_path)

        summary_text = None
        if generate_summary:
            raw_text = summary_service.build_text(translated_segments)
            summary_text = summary_service.summarize(
                raw_text, paths["summary"],
                sentences_count=summary_sentences,
                storage_manager=storage_manager
            )

        total_duration = time.time() - job_overall_start
        logger.info(f"[{request_id}] == JOB COMPLETED == {total_duration:.1f}s ({total_duration/60:.1f} min)")

        job_manager.update_progress(job_id, 100)
        job_manager.save_result(job_id, {
            "video_id": video_id,
            "video_url": final_video_url,
            "subtitles": paths["srt_lang"],
            "summary": summary_text
        })

    except Exception as e:
        current_status = job_manager.get_job(job_id)["status"]
        if current_status != STATUS_CANCELLED:
            logger.error(f"[{request_id}] Job {job_id} FAILED at '{current_status}': {str(e)}")
            logger.error(traceback.format_exc())
            job_manager.fail_job(job_id, {"error": str(e)})


@app.post("/upload-video")
async def upload_video(
    file: UploadFile = File(...),
    target_language: str = "he",
    generate_summary: bool = True,
    summary_sentences: int = 3
):
    MAX_FILE_SIZE_MB = 2000
    if file.size and file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (Max 2GB)")

    storage_manager.cleanup_if_needed()
    file_path = await asyncio.to_thread(video_source_service.save_uploaded_file, file)
    request_id = str(uuid.uuid4())[:8]
    job_id = job_manager.create_job()
    job_manager.update_status(job_id, STATUS_QUEUED)
    queue_service.add_job(
        process_video_job,
        job_id, file_path, request_id, target_language, generate_summary, summary_sentences
    )
    return {
        "status": STATUS_QUEUED,
        "job_id": job_id,
        "queue_position": queue_service.get_position(job_id)
    }


@app.post("/process-video")
def process_video(request: VideoRequest):
    storage_manager.cleanup_if_needed()
    request_id = str(uuid.uuid4())[:8]
    job_id = job_manager.create_job()
    job_manager.update_status(job_id, STATUS_QUEUED)
    queue_service.add_job(
        process_video_job,
        job_id, request.url, request_id,
        request.target_language, request.generate_summary, request.summary_sentences
    )
    return {
        "status": STATUS_QUEUED,
        "job_id": job_id,
        "queue_position": queue_service.get_position(job_id)
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
    if job["status"] == STATUS_QUEUED:
        response["queue_position"] = queue_service.get_position(job_id)
    if job.get("result"):
        response["result"] = job["result"]
    return response


@app.get("/health")
def health():
    return {
        "status": "ok" if transcription_service.model is not None else "degraded",
        "model_loaded": transcription_service.model is not None,
        "model_used": MODEL_SIZE,
        "timestamp": time.time()
    }


@app.get("/queue-status")
def get_queue_info():
    return {"queue_size": queue_service.get_queue_size(), "status": "active"}


@app.post("/cancel/{job_id}")
def cancel_video_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    job_manager.cancel_job(job_id)
    return {"status": "cancelled"}


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
            "subtitles": count_files(f"{STORAGE_PATH}/subtitles"),
        },
        "system_info": {
            "log_file_exists": os.path.exists(LOG_FILE),
            "server_time": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    }
