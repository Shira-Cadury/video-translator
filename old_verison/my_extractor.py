import yt_dlp

def download_audio(video_url):
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': '%(title)s.%(ext)s', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info_dict)
            
            print(f"Download complete: {filename}")
            return filename
        
    except Exception as e:
        print(f"somthing went worng: {e}")   
        return None
if __name__ == "__main__":        
    test_link = "https://youtu.be/xn0HzluujXk?si=Kk73VoIBuaD24wCo"  
    download_audio(test_link)           