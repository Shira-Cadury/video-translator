import yt_dlp
import os

class VideoService:
    def __init__(self):
        self.download_path = os.path.join("storage", "audio")
        
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
            
            
    def download_audio(self, url):
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(self.download_path, '%(id)s.%(ext)s'),
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        } 
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                duration_sec = info.get('duration', 0)
                
                print(f"Duration: {duration_sec} seconds")
                
                if duration_sec > 1200:
                    return {"status": "error", "message": "Video is too long (max 20 min)"}
                
                print(f"Downloading: {info.get('title')}...")
                ydl.download([url])
                file_path = os.path.join(self.download_path, f"{info.get('id')}.mp3")
                
                return {
                    "status": "success",
                    "file_path": file_path,
                    "title": info.get('title')
                }
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
        
        
if __name__ == "__main__":
    print("--- Video Service is starting ---")
    service = VideoService()
    test_url = "https://youtu.be/LEjhY15eCx0?si=62BU8REBu1wYO_GU" 
    print(service.download_audio(test_url))              