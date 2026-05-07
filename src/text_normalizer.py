"""
Модуль для лингвистической нормализации текста.

Выполняет очистку текста от технического "шума", нормализацию пробелов,
переносов строк и других элементов форматирования.
"""

import re
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NormalizationStats:
    """Статистика выполнения нормализации."""
    
    original_length: int = 0
    normalized_length: int = 0
    spaces_removed: int = 0
    linebreaks_normalized: int = 0
    special_chars_removed: int = 0
    
    def to_dict(self):
        """Преобразует статистику в словарь."""
        return {
            "original_length": self.original_length,
            "normalized_length": self.normalized_length,
            "spaces_removed": self.spaces_removed,
            "linebreaks_normalized": self.linebreaks_normalized,
            "special_chars_removed": self.special_chars_removed
        }


class TextNormalizer:
    """Основной класс для нормализации текста."""
    
    def __init__(self, 
                 preserve_formula_placeholders: bool = True,
                 aggressive_normalization: bool = False):
        """
        Инициализирует нормализатор.
        
        Args:
            preserve_formula_placeholders: Если True, сохраняет плейсхолдеры формул
            aggressive_normalization: Если True, применяет более агрессивную очистку
        """
        self.preserve_formula_placeholders = preserve_formula_placeholders
        self.aggressive_normalization = aggressive_normalization
        self.stats = NormalizationStats()
        
        # Регулярные выражения для разных типов нормализации
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Компилирует регулярные выражения для нормализации."""
        
        # Удаление BOM (Byte Order Mark) и других невидимых символов
        self.bom_pattern = re.compile(r'^\ufeff|\ufffe|\ufeff|\u200b|\u200c|\u200d|\ufeff', re.UNICODE)
        
        # Нормализация пробелов: множественные пробелы -> один пробел
        self.multi_space_pattern = re.compile(r'[ \t]+')
        
        # Нормализация переносов строк
        self.linebreak_pattern = re.compile(r'\r\n|\r')
        
        # Удаление лишних переносов строк (более 2 подряд -> 2)
        self.multi_linebreak_pattern = re.compile(r'\n{3,}')
        
        # Специальные символы, которые нужно удалить (но не из формул!)
        self.special_chars_pattern = re.compile(
            r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'  # Управляющие символы
        )
        
        # Нормализация кавычек (замена "ёлочек" и „лапок“ на обычные)
        self.quotes_pattern = re.compile(r'[«»„‟"＂]')
        
        # Нормализация дефисов и тире
        self.dash_pattern = re.compile(r'[–—]')
        
        # Символы, которые могут быть в формулах и которые нужно сохранить
        self.formula_safe_chars = set('+-*/=^_<>()[]{}|\\$')
        
        logger.debug("Паттерны нормализации скомпилированы")

    def _remove_hyphen_linebreaks(self, text: str) -> str:
        """
        Удаляет паттерны '-\n' (дефис и перевод строки) для склеивания разорванных слов.
        """
        # Удаляем дефис и следующий за ним перевод строки (учитывая \r\n на Windows)
        return re.sub(r'-\r?\n', '', text)
    
    def normalize(self, text: str) -> Tuple[str, NormalizationStats]:
        """
        Основной метод нормализации текста.
        
        Args:
            text: Исходный текст для нормализации
            
        Returns:
            Кортеж (нормализованный текст, статистика)
        """
        if not text or not isinstance(text, str):
            logger.warning("Получен пустой или нестроковый текст")
            return text if text else "", NormalizationStats()
        
        # Сохраняем оригинальную длину
        original_length = len(text)
        
        # Шаг 1: Удаление BOM и невидимых символов
        text = self._remove_bom(text)
        
        # Шаг 2: Нормализация переносов строк
        text = self._normalize_linebreaks(text)
        # Удаляем переносы слов через дефис
        text = self._remove_hyphen_linebreaks(text)
        
        # Шаг 3: Удаление специальных символов (кроме формул)
        text = self._remove_special_chars(text)
        
        # Шаг 4: Нормализация пробелов
        text = self._normalize_spaces(text)
        
        # Шаг 5: Нормализация кавычек и пунктуации (опционально)
        if self.aggressive_normalization:
            text = self._normalize_punctuation(text)
        
        # Обновляем статистику
        self.stats.original_length = original_length
        self.stats.normalized_length = len(text)
        
        logger.info(f"Текст нормализован: {original_length} -> {len(text)} символов")
        
        return text, self.stats
    
    
    def _remove_bom(self, text: str) -> str:
        """Удаляет BOM и невидимые символы из начала текста."""
        original_len = len(text)
        text = self.bom_pattern.sub('', text)
        removed = original_len - len(text)
        if removed > 0:
            logger.debug(f"Удалено BOM/невидимых символов: {removed}")
        return text
    
    def _normalize_linebreaks(self, text: str) -> str:
        """Нормализует переносы строк к единому стандарту (\n)."""
        # Простая замена без regex
        text = text.replace('\r\n', '\n')  # Windows
        text = text.replace('\r', '\n')    # Mac old
        
        # Удаляем избыточные переносы (оставляем максимум 2 подряд)
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')
        
        # Удаляем переносы в начале и конце текста
        text = text.strip('\n')
        
        return text
    
    def _remove_special_chars(self, text: str) -> str:
        """
        Удаляет специальные символы, сохраняя возможные формулы.
        
        Args:
            text: Текст для очистки
            
        Returns:
            Очищенный текст
        """
        if self.preserve_formula_placeholders:
            # Если нужно сохранить формулы, делаем это более аккуратно
            # Пока просто удаляем управляющие символы
            return self.special_chars_pattern.sub('', text)
        else:
            # Более агрессивная очистка
            return self.special_chars_pattern.sub('', text)
    
    def _normalize_spaces(self, text: str) -> str:
        """Нормализует пробелы и табуляции."""
        # Заменяем табы и множественные пробелы на один пробел
        text = self.multi_space_pattern.sub(' ', text)
        
        # Удаляем пробелы в начале и конце строк
        lines = text.split('\n')
        normalized_lines = [line.strip() for line in lines]
        text = '\n'.join(normalized_lines)
        
        # Удаляем лишние пробелы вокруг переносов строк
        text = re.sub(r' *\n *', '\n', text)
        
        return text
    
    def _normalize_punctuation(self, text: str) -> str:
        """Нормализует пунктуацию (кавычки, тире и т.д.)."""
        # Нормализация кавычек (замена на обычные двойные)
        text = self.quotes_pattern.sub('"', text)
        
        # Нормализация тире (замена на обычное тире)
        text = self.dash_pattern.sub('-', text)
        
        # Убираем лишние пробелы перед пунктуацией
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        
        # Добавляем пробелы после пунктуации, если нужно
        text = re.sub(r'([.,;:!?])([А-Яа-яA-Za-z])', r'\1 \2', text)
        
        return text
    
    def normalize_whitespace_only(self, text: str) -> str:
        """
        Только нормализация пробелов и переносов строк.
        Полезно для предобработки перед поиском формул.
        
        Args:
            text: Исходный текст
            
        Returns:
            Текст с нормализованными пробелами
        """
        text = self.linebreak_pattern.sub('\n', text)
        text = self.multi_space_pattern.sub(' ', text)
        text = text.strip()
        return text

def normalize_text(text: str, **kwargs) -> str:
    """
    Функция для быстрой нормализации текста.
    
    Args:
        text: Текст для нормализации
        **kwargs: Аргументы для TextNormalizer
        
    Returns:
        Нормализованный текст
    """
    normalizer = TextNormalizer(**kwargs)
    normalized, _ = normalizer.normalize(text)
    return normalized


def normalize_whitespace(text: str) -> str:
    """
    Быстрая нормализация только пробелов и переносов строк.
    
    Args:
        text: Текст для нормализации
        
    Returns:
        Текст с нормализованными пробелами
    """
    normalizer = TextNormalizer()
    return normalizer.normalize_whitespace_only(text)

