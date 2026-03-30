from deep_translator import GoogleTranslator

def translate_to_hebrew(text):
    if not text or not text.strip():
        return "Error: No text provided"
    
    try:
        print("Translating with deep-translator...")
        translated = GoogleTranslator(source='auto', target='iw').translate(text)
        
        return translated
    except Exception as e:
        return f"The translation failed because: {e}"

if __name__ == "__main__":
    print(translate_to_hebrew("I am a software engineer and I love to code!"))