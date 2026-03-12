import whisper
import os

class TranscriptionService:
    model = None

    def __init__(self):
        if TranscriptionService.model is None:
            print("Loading Whisper model ('base')...")
            try:
                TranscriptionService.model = whisper.load_model("base")
                print("Model loaded successfully.")
            except Exception as e:
                print(f"Failed to load model: {e}")

        self.model = TranscriptionService.model
        
    def transcribe(self, audio_path):
        if self.model is None:
            return {
                "success": False,
                "error": "Model not loaded"
            }
        if not os.path.exists(audio_path):
            return {"success": False, "error": f"File not found: {audio_path}"}

        print(f"Starting transcription: {audio_path}")
        
        try:
            result = self.model.transcribe(audio_path)
            
            return {
                "success": True,
                "text": result.get("text", ""),
                "segments": result.get("segments", []),
                "language": result.get("language", "")
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

if __name__ == "__main__":
    service = TranscriptionService()
    test_audio = r"storage\audio\LEjhY15eCx0.mp3"
    
    result = service.transcribe(test_audio) 
    
    if result["success"]:
        print("\n--- Transcription Success! ---")
        print(result["text"][:500] + "...") 
        print("------------------------------")
    else:
        print(f"Transcription failed: {result.get('error')}")