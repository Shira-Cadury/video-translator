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

if not os.path.exists("storage"):
    os.makedirs("storage")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

class VideoRequest(BaseModel):
    url: str

@app.get("/")
def root():
    return {"message": "Video Translator API is running and healthy"}

@app.post("/process-video")
def process_video(request: VideoRequest):
    start_time = time.time()
    url = request.url
    print(f"\nReceived new request for: {url}")
    
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not video_id_match:
        return {"status": "error", "message": "Invalid YouTube URL"}
    
    video_id = video_id_match.group(1)
    summary_he_path = f"storage/subtitles/{video_id}_summary_he.txt"
    
    if os.path.exists(summary_he_path):
        print(f"[Cache Hit] Found existing work for {video_id}")
        with open(summary_he_path, "r", encoding="utf-8") as f:
            cached_summary = f.read()
        return {
            "status": "success",
            "source": "cache",
            "video_id": video_id,
            "summary": cached_summary,
            "processing_time": "0 seconds (cached)",
            "files": {
                "english_srt": f"storage/subtitles/{video_id}.srt",
                "hebrew_srt": f"storage/subtitles/{video_id}_he.srt"
            }
        }

    print(f"Starting full process for {video_id}")

    download_res = video_service.download_audio(url)
    if download_res["status"] != "success":
        return {"status": "error", "message": f"Download failed: {download_res.get('message')}"}
    audio_path = download_res["file_path"]

    trans_res = transcription_service.transcribe(audio_path)
    if not trans_res["success"]:
        return {"status": "error", "message": "Transcription engine failed"}
    segments = trans_res["segments"]

    srt_en_path = f"storage/subtitles/{video_id}.srt"
    json_path = f"storage/subtitles/{video_id}.json"
    subtitle_service.generate_srt(segments, srt_en_path)
    subtitle_service.save_transcript_json(trans_res, json_path)

    print("Translating to Hebrew...")
    heb_segments = translation_service.translate_segments(segments)
    srt_he_path = f"storage/subtitles/{video_id}_he.srt"
    subtitle_service.generate_srt(heb_segments, srt_he_path)

    print("Generating summary...")
    hebrew_text = summary_service.build_text_from_segments(heb_segments)
    video_summary = summary_service.generate_summary(hebrew_text, sentences_count=3)

    with open(summary_he_path, "w", encoding="utf-8") as f:
        f.write(video_summary)

    total_time = round(time.time() - start_time, 2)
    print(f"Finished! Total time: {total_time}s")

    return {
        "status": "success",
        "source": "newly_processed",
        "video_id": video_id,
        "processing_time": f"{total_time} seconds",
        "summary": video_summary,
        "files": {
            "english_srt": srt_en_path,
            "hebrew_srt": srt_he_path,
            "transcript_json": json_path
        }
    }