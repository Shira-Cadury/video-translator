from my_extractor import download_audio
from transcriber import transcribe_audio
from translator import translate_to_hebrew

def run_translator():
    link = input("Please insert a YouTube link: ")
    
    print("\n[1/3] Downloading audio")
    audio_file = download_audio(link)
    
    if audio_file is None:
        print("Stopping process because download failed.")
        return 

    print(f"\n[2/3] Transcribing and translating to English: {audio_file}")
    english_text = transcribe_audio(audio_file)
    
    print("\n[3/3] Final translation to Hebrew...")
    hebrew_text = translate_to_hebrew(english_text)
    
    print("\n" + "="*30)
    print("FINAL HEBREW TRANSLATION:")
    print("="*30)
    print(hebrew_text)

if __name__ == "__main__":
    run_translator()