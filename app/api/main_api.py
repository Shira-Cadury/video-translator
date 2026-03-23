from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
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
    
    
@app.post("/process-video")
def process_video(request: VideoRequest):
    request_id = str(uuid.uuid4())[:8]
    try:
        start_time = time.time()
        url = request.url
        lang = request.target_language 
        
        logger.info(f"[{request_id}] Request received: {url} | Lang: {lang}")
        
        video_id = extract_video_id(url)
        paths = get_video_paths(video_id, lang=lang)
        
        try:
            duration = video_service.get_video_duration(url)
            if duration > 1200:
                logger.warning(f"[{request_id}] Long video: {duration}s. Expect delay.")
        except Exception as e:
            logger.warning(f"[{request_id}] Duration check skipped: {e}")

        video_file_path = f"storage/video/{video_id}.mp4"
        
        if os.path.exists(paths["trans"]) and os.path.exists(video_file_path):
            if not request.generate_summary or os.path.exists(paths["summary"]):
                logger.info(f"[{request_id}] Super Fast Cache Hit! No network calls needed.")
                
                summary_text = None
                if request.generate_summary and os.path.exists(paths["summary"]):
                    with open(paths["summary"], "r", encoding="utf-8") as f:
                        summary_text = f.read()
                
                return {
                    "status": "success", "request_id": request_id, "video_id": video_id,
                    "source": "cache", "language": lang, "summary": summary_text,
                    "video": video_file_path, "processing_time": "0s (cached)"
                }

        logger.info(f"[{request_id}] [START] Full process for {video_id}")
        
        video_res = video_service.download_video(url)
        
        MAX_SIZE_MB = 500
        actual_size = os.path.getsize(video_res['file_path']) / (1024 * 1024)
        if actual_size > MAX_SIZE_MB:
            os.remove(video_res['file_path']) 
            logger.error(f"[{request_id}] File too large: {actual_size:.2f}MB")
            raise HTTPException(status_code=413, detail=f"Video too heavy (Max {MAX_SIZE_MB}MB)")

        audio_path = video_service.download_audio(url)["file_path"]
        segments = transcription_service.transcribe(audio_path, paths["json"])["segments"]
        
        translated_segments = translation_service.translate_segments(
            segments, paths["trans"], target_lang=lang
        )
        subtitle_service.generate_srt(translated_segments, paths["srt_lang"]) 

        video_summary = None
        if request.generate_summary:
            raw_text = summary_service.build_text(translated_segments)
            video_summary = summary_service.summarize(
                raw_text, paths["summary"], sentences_count=request.summary_sentences
            )

        total_time = round(time.time() - start_time, 2)
        logger.info(f"[{request_id}] Finished in {total_time}s")

        return {
            "status": "success", "request_id": request_id, "video_id": video_id,
            "source": "processed", "language": lang, "summary": video_summary,
            "video": video_res['file_path'], "subtitles_vtt": paths["vtt_lang"],
            "processing_time": f"{total_time}s"
        }

    except HTTPException as e:
        raise e 
    except Exception as e:
        logger.error(f"[{request_id}] Fatal: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))