import re
import logging

logger = logging.getLogger(__name__)

class MarkdownCleaner:
    def __init__(self):
        # Шаблон для поиска LaTeX-формул: $...$ и $$...$$
        self.formula_pattern = re.compile(r'(\$\$.*?\$\$|\$.*?\$)', re.DOTALL)

    def clean(self, text: str) -> str:
        # 1. Временно сохраняем все $...$ и $$...$$ в плейсхолдеры
        placeholders = {}
        counter = [0]

        def save_formula(match):
            key = f"<<<MD_FORMULA_{counter[0]}>>>"
            placeholders[key] = match.group(0)
            counter[0] += 1
            return key

        text = self.formula_pattern.sub(save_formula, text)

        # 2. Удаляем Markdown-разметку (безопасно для плейсхолдеров формул)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)               # изображения
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)     # ссылки
        text = re.sub(r'\*\*\*(.*?)\*\*\*', r'\1', text)         # жирный+курсив
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)             # жирный
        text = re.sub(r'__(.*?)__', r'\1', text)                 # жирный 2
        text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'\1', text)  # курсив *
        text = re.sub(r'\b_(.*?)_\b', r'\1', text)               # курсив _
        text = re.sub(r'~~(.*?)~~', r'\1', text)                 # зачёркивание
        text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)    # цитаты
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # заголовки
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)  # маркированные списки
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)  # нумерованные списки

        # 3. Нормализация пробелов и переводов строк
        # Схлопываем множественные пробелы
        text = re.sub(r'[ \t]+', ' ', text)
        # Убираем одиночные пробелы вокруг переводов строки
        text = re.sub(r' *\n *', '\n', text)
        # Заменяем 3 и более переводов строки на два (оставляем абзацы)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # 4. Восстанавливаем формулы на место
        for key, formula in placeholders.items():
            text = text.replace(key, formula)

        return text