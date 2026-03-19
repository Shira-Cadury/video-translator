import yt_dlp
import os
class VideoService:
    def __init__(self):
        self.audio_path = os.path.join("storage", "audio")
        self.video_path = os.path.join("storage", "video")

        for path in [self.audio_path, self.video_path]:
            os.makedirs(path, exist_ok=True)


    def download_audio(self, url):
        """Download audio (MP3) for transcription"""

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(self.audio_path, '%(id)s.%(ext)s'),
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

                if info.get('duration', 0) > 1200:
                    return {
                        "status": "error",
                        "message": "Video is too long (max 20 min)"
                    }

                video_id = info.get('id')
                title = info.get('title')

                file_path = os.path.join(self.audio_path, f"{video_id}.mp3")

                if os.path.exists(file_path):
                    print(f"Audio found in cache: {file_path}")
                    return {
                        "status": "success",
                        "file_path": file_path,
                        "title": title
                    }

                print(f"Downloading Audio: {title}")
                ydl.download([url])

                return {
                    "status": "success",
                    "file_path": file_path,
                    "title": title
                }

        except Exception as e:
            print(f"Audio download error: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

   
   
    def download_video(self, url):
        """Download video (MP4) for frontend player"""

        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': os.path.join(self.video_path, '%(id)s.%(ext)s'),
            'quiet': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                info = ydl.extract_info(url, download=False)

                if info.get('duration', 0) > 1200:
                    return {
                        "status": "error",
                        "message": "Video is too long (max 20 min)"
                    }

                video_id = info.get('id')
                title = info.get('title')
                ext = info.get("ext") or "mp4"

                file_path = os.path.join(self.video_path, f"{video_id}.{ext}")

                if os.path.exists(file_path):
                    print(f"Video found in cache: {file_path}")
                    return {
                        "status": "success",
                        "file_path": file_path,
                        "title": title
                    }

                print(f"Downloading Video: {title}")
                ydl.download([url])

                print(f"Video downloaded: {file_path}")

                return {
                    "status": "success",
                    "file_path": file_path,
                    "title": title
                }

        except Exception as e:
            print(f"Video download error: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }