from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles 
from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
from app.services.translation_service import TranslationService
from app.services.summary_service import SummaryService
import os
import re
import time
import logging
import uuid

video_service = VideoService()
transcription_service = TranscriptionService()
subtitle_service = SubtitleService()
translation_service = TranslationService()
summary_service = SummaryService()

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

def extract_video_id(url: str):
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not video_id_match:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL format")
    return video_id_match.group(1)

def get_video_paths(video_id: str):
    return {
        "json": f"storage/subtitles/{video_id}.json",
        "trans_he": f"storage/subtitles/{video_id}_he.json",
        "summary": f"storage/subtitles/{video_id}_summary_he.txt",
        "srt_en": f"storage/subtitles/{video_id}.srt",
        "srt_he": f"storage/subtitles/{video_id}_he.srt",
        "vtt_he": f"storage/subtitles/{video_id}_he.vtt"
    }

@app.get("/")
def root():
    return {"message": "Video Translator API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "1.0.0"}

@app.post("/process-video")
def process_video(request: VideoRequest):
    request_id = str(uuid.uuid4())[:8]
    try:
        start_time = time.time()
        url = request.url
        
        logger.info(f"[{request_id}] Started processing: {url}")
        
        video_id = extract_video_id(url)
        paths = get_video_paths(video_id)
        
        MAX_DURATION = 1200 
        try:
            duration = video_service.get_video_duration(url)
            if duration > MAX_DURATION:
                logger.warning(f"[{request_id}] Video too long: {duration}s")
                raise HTTPException(status_code=400, detail="Video is too long (max 20 minutes)")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"[{request_id}] Could not check duration: {e}")

        if os.path.exists(paths["summary"]) and os.path.exists(paths["vtt_he"]):
            logger.info(f"[{request_id}] [CACHE] Fast-track hit for {video_id}")
            video_res = video_service.download_video(url)
            with open(paths["summary"], "r", encoding="utf-8") as f:
                return {
                    "status": "success",
                    "request_id": request_id,
                    "source": "cache",
                    "summary": f.read(),
                    "video": video_res['file_path'],
                    "subtitles_vtt": paths['vtt_he'],
                    "processing_time": "0s (cached)"
                }

        logger.info(f"[{request_id}] [START] Full process for {video_id}")

        video_res = video_service.download_video(url)
        
        audio_path = video_service.download_audio(url)["file_path"]
        segments = transcription_service.transcribe(audio_path, paths["json"])["segments"]
        
        subtitle_service.generate_srt(segments, paths["srt_en"])
        heb_segments = translation_service.translate_segments(segments, paths["trans_he"])
        subtitle_service.generate_srt(heb_segments, paths["srt_he"]) 

        raw_text = summary_service.build_text(heb_segments)
        video_summary = summary_service.summarize(raw_text, paths["summary"])

        total_time = round(time.time() - start_time, 2)
        logger.info(f"[{request_id}] [FINISHED] Total: {total_time}s")

        return {
            "status": "success",
            "request_id": request_id,
            "source": "processed",
            "summary": video_summary,
            "video": video_res['file_path'],
            "subtitles_vtt": paths['vtt_he'],
            "processing_time": f"{total_time}s"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"[{request_id}] [FATAL ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))