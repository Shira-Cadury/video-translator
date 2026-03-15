from deep_translator import GoogleTranslator

class TranslationService:
    def __init__(self, source="auto", target="iw"):
        self.translator = GoogleTranslator(source=source, target=target)
        
        
    def translate_segments(self, segments):
        if not segments:
            return []
        
        translated_list = []
        for segment in segments:
            english_text = segment.get("text", "")
            
            try:
                hebrew_text = self.translator.translate(english_text)
            except Exception:
                hebrew_text = english_text    
            
            new_segment = {
                "start": segment["start"],
                "end": segment["end"],
                "text": hebrew_text
            } 
            
            translated_list.append(new_segment)
        return translated_list 
    
    
    
if __name__ == "__main__":
    service = TranslationService()
    test_data = [
        {"start": 0.0, "end": 2.0, "text": "I love programming"},
        {"start": 2.0, "end": 5.0, "text": "Python is a great language"}
    ]
    
    print("Translating... please wait")
    result = service.translate_segments(test_data)
    
    for seg in result:
        print(f"{seg['start']} --> {seg['end']}: {seg['text']}")       