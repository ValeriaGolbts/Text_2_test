import re
import logging

logger = logging.getLogger(__name__)

class LectureTextCleaner:
    def __init__(self):
        self.irrelevant_phrases = [
            r"добрый день", r"добрый вечер", r"здравствуйте", r"здрасьте",
            r"всем привет", r"приветствую", r"перерыв", r"вопросы есть",
            r"какие вопросы", r"начинаем", r"заканчиваем", r"до свидания",
            r"спасибо за внимание", r"ладно", r"так", r"следующая тема",
            r"перейдём к следующему", r"как вы помните", r"давайте вспомним",
        ]
        self.patterns = [re.compile(rf"\b{phrase}\b", re.IGNORECASE) for phrase in self.irrelevant_phrases]

    def clean(self, text: str) -> str:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        kept = []
        for sent in sentences:
            if any(p.search(sent) for p in self.patterns):
                continue
            if len(sent.strip()) < 10:
                continue
            kept.append(sent)
        cleaned = ' '.join(kept)
        logger.info(f"Очистка текста: {len(sentences)} -> {len(kept)} предложений")
        return cleaned