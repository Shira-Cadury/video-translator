from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService
from app.services.subtitle_service import SubtitleService
from app.services.translation_service import TranslationService
from app.services.summary_service import SummaryService
import os
import time

def run_translator():
    video_service = VideoService()
    transcriber = TranscriptionService()
    subtitle_service = SubtitleService()
    translator = TranslationService()
    summary_service = SummaryService()
    
    user_input = input("Please enter a YouTube link OR a local file path: ").strip()
    
    start_total = time.time()
    
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
    
    print("\nGenerating AI Summary in Hebrew")
    hebrew_text_for_summary = summary_service.build_text_from_segments(heb_segments)
    video_summary = summary_service.generate_summary(hebrew_text_for_summary, sentences_count=3)
    
    summary_path = f"storage/subtitles/{video_id}_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(video_summary)
        
    print("\n" + "="*30)
    print("VIDEO SUMMARY (HEBREW):")
    print(video_summary)
    print("="*30)
    
    total_time = round(time.time() - start_total, 2)
    print(f"\nDone! Total process took {total_time} seconds.")    

if __name__ == "__main__":
    run_translator()