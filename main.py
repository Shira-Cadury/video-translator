from app.services.video_service import VideoService
from app.services.transcription_service import TranscriptionService

def run_translator():
    video_tool = VideoService()
    ai_tool = TranscriptionService()
    url = "https://youtu.be/CkLiND6qa34?si=GgYXGMWb0eBp1JMg"
    print("\n---Downloading audio from YouTube---")
    video_res = video_tool.download_audio(url)
    if video_res.get("status") == "success":
        audio_path = video_res.get("file_path")
        
        print("\n---Transcription with the help of Whisper---")
        transcript_res = ai_tool.transcribe(audio_path)
    
        if transcript_res["success"]:
            print("\nThe project work")
            print("-" * 30)
            print(f"languag: {transcript_res['language']}") 
            print(f"text: {transcript_res['text'][:300]}")  
            print("-" * 30)
        else:
            print(f"Transcription error: {transcript_res.get('error')}")
    else:
        print(f"Transcription error: {video_res.get('message')}")        
        
        
        
        
if __name__ == "__main__":
    run_translator()