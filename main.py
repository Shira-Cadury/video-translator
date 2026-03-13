from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
import os

def run_translator():
    video_service = VideoService()
    transcriber = TranscriptionService()
    subtitle_service = SubtitleService()
    
    link = input("Pleas enter a link")
    download_res = video_service.download_audio(link)
    
    if download_res["status"] != "success":
        print(f"The download fail: {download_res.get('message')}")
        return
    
    audio_path = download_res["file_path"]
    transcription_result = transcriber.transcribe(audio_path)
    
    if not transcription_result["success"]:
        print(f"Transcription failed: {transcription_result.get('error')}")
        return
    
    filename = os.path.basename(audio_path)
    video_id = os.path.splitext(filename)[0]
    
    srt_path = f"storage/subtitles/{video_id}.srt"
    json_path = f"storage/subtitles/{video_id}.json"
    subtitle_service.generate_srt(transcription_result["segments"], srt_path)
    subtitle_service.save_transcript_json(transcription_result, json_path)
    print(f"Success! Subtitles saved to: {srt_path}")
        
        
if __name__ == "__main__":
    run_translator()