from fastapi import FastAPI
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
import json

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

os.makedirs("storage", exist_ok=True)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

class VideoRequest(BaseModel):
    url: str


def extract_video_id(url: str):
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not video_id_match:
        raise Exception("Invalid YouTube URL")
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

def handle_audio(url: str):
    start = time.time()
    res = video_service.download_audio(url) 
    if res["status"] != "success":
        raise Exception(f"Audio download failed: {res.get('message')}")
    print(f"[TIME] Audio: {time.time()-start:.2f}s")
    return res["file_path"]

def handle_transcription(audio_path: str, json_path: str):
    start = time.time()
    res = transcription_service.transcribe(audio_path, json_path)
    if not res["success"]:
        raise Exception("Transcription failed")
    
    source = "CACHE" if res.get("from_cache") else "WHISPER"
    print(f"[TIME] Transcription ({source}): {time.time()-start:.2f}s")
    return res["segments"]

def handle_translation(segments, trans_he_path: str):
    start = time.time()
    heb_segments = translation_service.translate_segments(segments, trans_he_path)
    print(f"[TIME] Translation: {time.time()-start:.2f}s")
    return heb_segments

def handle_summary(heb_segments, summary_path: str):
    start = time.time()
    raw_text = summary_service.build_text(heb_segments)
    video_summary = summary_service.summarize(raw_text, summary_path)
    print(f"[TIME] Summary: {time.time()-start:.2f}s")
    return video_summary


@app.get("/")
def root():
    return {"message": "Video Translator API is running and healthy"}

@app.post("/process-video")
def process_video(request: VideoRequest):
    try:
        start_time = time.time()
        url = request.url
        
        video_id = extract_video_id(url)
        paths = get_video_paths(video_id)

        if os.path.exists(paths["summary"]) and os.path.exists(paths["vtt_he"]):
            print(f"[API CACHE] Fast-track hit for {video_id}")
            video_res = video_service.download_video(url)
            with open(paths["summary"], "r", encoding="utf-8") as f:
                return {
                    "status": "success",
                    "source": "cache",
                    "summary": f.read(),
                    "video": video_res['file_path'],
                    "subtitles_vtt": paths['vtt_he'],
                    "processing_time": "0s (cached)"
                }

        print(f"[START] Full process for {video_id}")

        video_res = video_service.download_video(url)
        audio_path = handle_audio(url)
        
        segments = handle_transcription(audio_path, paths["json"])
        subtitle_service.generate_srt(segments, paths["srt_en"])
        subtitle_service.save_transcript_json(segments, paths["json"]) 

        heb_segments = handle_translation(segments, paths["trans_he"])
        subtitle_service.generate_srt(heb_segments, paths["srt_he"]) 

        video_summary = handle_summary(heb_segments, paths["summary"])

        total_time = round(time.time() - start_time, 2)
        print(f"[FINISHED] Total: {total_time}s")

        return {
            "status": "success",
            "source": "processed",
            "summary": video_summary,
            "video": video_res['file_path'],
            "subtitles_vtt": paths['vtt_he'],
            "processing_time": f"{total_time}s"
        }

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}