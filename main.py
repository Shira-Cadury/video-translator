from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
from app.services.translation_service import TranslationService
import os

def run_translator():
    video_service = VideoService()
    transcriber = TranscriptionService()
    subtitle_service = SubtitleService()
    translator = TranslationService()
    
    user_input = input("Please enter a YouTube link OR a local file path: ").strip()
    
    if os.path.exists(user_input):
        audio_path = user_input
        print(f"Using local file: {audio_path}")
    else:
        print("Link detected, starting download...")
        download_res = video_service.download_audio(user_input)
        
        if download_res["status"] != "success":
            print(f"The download failed: {download_res.get('message')}")
            return
        audio_path = download_res["file_path"]
    
    print("Transcribing (this might take a few minutes)")
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
    print(f"English subtitles saved to: {srt_path}")
    
    print("Translating to Hebrew...")
    heb_segments = translator.translate_segments(transcription_result["segments"])
    
    srt_heb_path = f"storage/subtitles/{video_id}_he.srt"
    
    subtitle_service.generate_srt(heb_segments, srt_heb_path)
    print(f"Success! Hebrew subtitles saved to: {srt_heb_path}")

if __name__ == "__main__":
    run_translator()