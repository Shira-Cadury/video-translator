import re
import nltk
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

class SummaryService:
    
    def __init__(self):
        try:
            nltk.data.find('tokenizers/punkt')
            nltk.data.find('tokenizers/punkt_tab')
        except LookupError:
            nltk.download('punkt')
            nltk.download('punkt_tab')
            
    
    def build_text_from_segments(self, segments):
        if not segments:
            return ""
        
        all_text = [segment.get("text", "") for segment in segments]
        text = " ".join(all_text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
        
    
        
    def generate_summary(self, text, sentences_count=3):
        if not text or len(text) < 10:
            return "The text is too short for a summary."
        
        if len(text) > 10000:
            text = text[:10000]
            
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        summary_sentences = summarizer(parser.document, sentences_count)
        summary_result = "\n".join([f"• {str(sentence)}" for sentence in summary_sentences])        
        if not summary_result:
            return "Summary could not be generated"
        return summary_result
    