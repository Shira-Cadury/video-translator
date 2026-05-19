import whisper

def transcribe_audio(audio_path):
    print("Loading begins")
    model = whisper.load_model("base")
    print("Decoding is starting, this may take time.")
    result = model.transcribe(audio_path, task="translate")
    return result["text"]

if __name__ == "__main__":
    my_file = "[GOING SEVENTEEN] EP.118 고잉 제작기 ： 좀비와의 인터뷰 (GOING PRODUCTION ： Interview With The Zombie).webm"
    final_text = transcribe_audio(my_file)
    print("\n--- The Translation ---")
    print(final_text)