"""
Модуль для извлечения метаданных из текстовых блоков.

Предоставляет различные экстракторы для анализа содержания блоков:
- определение темы
- извлечение ключевых слов
- проверка наличия формул
- анализ сложности текста и т.д.
"""

import re
import logging
import math
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import Counter

from src.models import Formula, FormulaType

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Результат извлечения метаданных."""
    
    metadata: Dict[str, Any]
    """Извлеченные метаданные."""
    
    confidence: float
    """Уверенность в извлечении (0.0-1.0)."""
    
    extractor_name: str
    """Имя экстрактора."""


class MetadataExtractor(ABC):
    """Абстрактный базовый класс для экстракторов метаданных."""
    
    def __init__(self, name: str = None):
        """
        Инициализирует экстрактор.
        
        Args:
            name: Имя экстрактора (если None - используется имя класса)
        """
        self.name = name or self.__class__.__name__
        logger.debug(f"Инициализирован экстрактор: {self.name}")
    
    @abstractmethod
    def extract(self, text: str, context: Dict[str, Any] = None) -> ExtractionResult:
        """
        Извлекает метаданные из текста.
        
        Args:
            text: Текст для анализа
            context: Контекстная информация (например, формулы в тексте)
            
        Returns:
            Результат извлечения
        """
        pass
    
    def _clean_text(self, text: str) -> str:
        """Очищает текст для анализа."""
        # Удаляем плейсхолдеры формул
        text = re.sub(r'\[\[FORMULA_.*?\]\]', '', text)
        # Приводим к нижнему регистру
        text = text.lower()
        # Удаляем лишние пробелы
        text = ' '.join(text.split())
        return text


class FormulaPresenceExtractor(MetadataExtractor):
    """Экстрактор для проверки наличия формул в тексте."""
    
    def extract(self, text: str, context: Dict[str, Any] = None) -> ExtractionResult:
        """
        Проверяет наличие формул в тексте.
        
        Args:
            text: Текст для анализа
            context: Должен содержать ключ 'formulas' со списком Formula
            
        Returns:
            Результат с информацией о формулах
        """
        formulas = context.get('formulas', []) if context else []
        
        # Проверяем наличие плейсхолдеров формул в тексте
        has_formula_placeholders = bool(re.search(r'\[\[FORMULA_.*?\]\]', text))
        
        # Подсчитываем формулы по типам
        formula_types = {}
        if formulas:
            formula_types = {
                'latex_inline': len([f for f in formulas if f.formula_type == FormulaType.LATEX_INLINE]),
                'latex_display': len([f for f in formulas if f.formula_type == FormulaType.LATEX_DISPLAY]),
                'plain_text': len([f for f in formulas if f.formula_type == FormulaType.PLAIN_TEXT]),
                'total': len(formulas)
            }
        
        # Определяем уверенность
        confidence = 1.0 if formulas or has_formula_placeholders else 0.95
        
        metadata = {
            'has_formulas': len(formulas) > 0 or has_formula_placeholders,
            'formula_count': len(formulas),
            'formula_types': formula_types,
            'has_formula_placeholders': has_formula_placeholders
        }
        
        return ExtractionResult(metadata, confidence, self.name)


class TextStatisticsExtractor(MetadataExtractor):
    """Экстрактор для сбора статистики текста."""
    
    def __init__(self, name: str = None):
        super().__init__(name)
        # Список стоп-слов для русского и английского
        self.stop_words = self._load_stop_words()
    
    def extract(self, text: str, context: Dict[str, Any] = None) -> ExtractionResult:
        """
        Собирает статистику текста.
        
        Args:
            text: Текст для анализа
            context: Контекстная информация
            
        Returns:
            Результат со статистикой
        """
        cleaned_text = self._clean_text(text)
        
        # Разбиваем на слова
        words = re.findall(r'\b\w+\b', cleaned_text)
        
        # Разбиваем на предложения
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Считаем статистику
        word_count = len(words)
        sentence_count = len(sentences)
        char_count = len(text)
        
        # Средняя длина слова
        avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
        
        # Средняя длина предложения
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        
        # Считаем уникальные слова
        unique_words = len(set(words))
        lexical_diversity = unique_words / word_count if word_count > 0 else 0
        
        metadata = {
            'word_count': word_count,
            'sentence_count': sentence_count,
            'character_count': char_count,
            'avg_word_length': round(avg_word_length, 2),
            'avg_sentence_length': round(avg_sentence_length, 2),
            'unique_words': unique_words,
            'lexical_diversity': round(lexical_diversity, 3),
            'is_short': word_count < 50,
            'is_long': word_count > 500
        }
        
        # Уверенность высокая для статистики
        confidence = 0.99
        
        return ExtractionResult(metadata, confidence, self.name)
    
    def _load_stop_words(self) -> Set[str]:
        """Загружает список стоп-слов."""
        # Базовый список стоп-слов
        stop_words = {
            # Русские
            'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 
            'то', 'все', 'она', 'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же',
            'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от',
            'меня', 'еще', 'нет', 'о', 'из', 'ему', 'теперь', 'когда', 'даже',
            'ну', 'вдруг', 'ли', 'если', 'уже', 'или', 'ни', 'быть', 'был', 'него',
            'до', 'вас', 'нибудь', 'опять', 'уж', 'вам', 'ведь', 'там', 'потом',
            'себя', 'ничего', 'ей', 'может', 'они', 'тут', 'где', 'есть', 'надо',
            'ней', 'для', 'мы', 'тебя', 'их', 'чем', 'была', 'сам', 'чтоб', 'без',
            'будто', 'чего', 'раз', 'тоже', 'себе', 'под', 'будет', 'ж', 'тогда',
            'кто', 'этот', 'того', 'потому', 'этого', 'какой', 'совсем', 'ним',
            'здесь', 'этом', 'один', 'почти', 'мой', 'тем', 'чтобы', 'нее', 'сейчас',
            'были', 'куда', 'зачем', 'всех', 'никогда', 'можно', 'при', 'наконец',
            'два', 'об', 'другой', 'хоть', 'после', 'над', 'больше', 'тот', 'через',
            'эти', 'нас', 'про', 'всего', 'них', 'какая', 'много', 'разве', 'три',
            'эту', 'моя', 'впрочем', 'хорошо', 'свою', 'этой', 'перед', 'иногда',
            'лучше', 'чуть', 'том', 'нельзя', 'такой', 'им', 'более', 'всегда',
            'конечно', 'всю', 'между',
            
            # Английские
            'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall',
            'should', 'can', 'could', 'may', 'might', 'must', 'i', 'you', 'he',
            'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my',
            'your', 'his', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours',
            'theirs', 'this', 'that', 'these', 'those', 'am', 'not', 'so', 'too',
            'very', 'just', 'now', 'then', 'here', 'there', 'when', 'where', 'why',
            'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other',
            'some', 'such', 'no', 'nor', 'only', 'own', 'same', 'than', 'too',
            'very', 's', 't', 'don', 'don\'t', 'ain', 'aren', 'aren\'t', 'couldn',
            'couldn\'t', 'didn', 'didn\'t', 'doesn', 'doesn\'t', 'hadn', 'hadn\'t',
            'hasn', 'hasn\'t', 'haven', 'haven\'t', 'isn', 'isn\'t', 'ma', 'mightn',
            'mightn\'t', 'mustn', 'mustn\'t', 'needn', 'needn\'t', 'shan', 'shan\'t',
            'shouldn', 'shouldn\'t', 'wasn', 'wasn\'t', 'weren', 'weren\'t', 'won',
            'won\'t', 'wouldn', 'wouldn\'t'
        }
        
        return stop_words

class TopicExtractor(MetadataExtractor):
    """Экстрактор для определения темы текста."""
    
    def __init__(self, name: str = None, use_first_sentence: bool = True):
        """
        Инициализирует экстрактор тем.
        
        Args:
            name: Имя экстрактора
            use_first_sentence: Использовать ли первое предложение для определения темы
        """
        super().__init__(name)
        self.use_first_sentence = use_first_sentence
        
        # Ключевые слова для определения тем
        self.topic_keywords = {
            'математика': ['теорема', 'формула', 'уравнение', 'функция', 'интеграл', 
                          'производная', 'матрица', 'вектор', 'алгебра', 'геометрия'],
            'физика': ['закон', 'энергия', 'масса', 'скорость', 'ускорение', 'сила',
                      'заряд', 'поле', 'волна', 'квант', 'атом'],
            'информатика': ['алгоритм', 'программа', 'код', 'база', 'данные', 'сеть',
                           'сервер', 'клиент', 'интерфейс', 'бит', 'байт'],
            'программирование': ['python', 'java', 'javascript', 'функция', 'класс',
                                'объект', 'метод', 'переменная', 'цикл', 'условие'],
            'анализ': ['исследование', 'анализ', 'статистика', 'данные', 'тренд',
                      'корреляция', 'регрессия', 'выборка', 'гипотеза'],
        }
    
    def extract(self, text: str, context: Dict[str, Any] = None) -> ExtractionResult:
        """
        Определяет тему текста.
        
        Args:
            text: Текст для анализа
            context: Контекстная информация
            
        Returns:
            Результат с определенной темой
        """
        cleaned_text = self._clean_text(text)
        
        # Стратегия 1: Использовать первое предложение
        if self.use_first_sentence:
            first_sentence = self._get_first_sentence(text)
            if first_sentence:
                topic_from_first = self._extract_topic_from_text(first_sentence)
                if topic_from_first:
                    return ExtractionResult(
                        {'main_topic': topic_from_first, 'source': 'first_sentence'},
                        0.8,
                        self.name
                    )
        
        # Стратегия 2: Анализ всего текста
        topic_from_full = self._extract_topic_from_text(cleaned_text)
        
        if topic_from_full:
            confidence = 0.7
            metadata = {'main_topic': topic_from_full, 'source': 'full_text'}
        else:
            # Стратегия 3: Использовать контекст (например, заголовок из metadata)
            if context and 'parent_metadata' in context:
                parent_topic = context['parent_metadata'].get('main_topic')
                if parent_topic:
                    return ExtractionResult(
                        {'main_topic': parent_topic, 'source': 'inherited'},
                        0.6,
                        self.name
                    )
            
            # Не удалось определить тему
            confidence = 0.3
            metadata = {'main_topic': 'неизвестно', 'source': 'unknown'}
        
        return ExtractionResult(metadata, confidence, self.name)
    
    def _get_first_sentence(self, text: str) -> str:
        """Извлекает первое предложение из текста."""
        # Ищем конец первого предложения
        match = re.search(r'^.*?[.!?]', text.strip())
        if match:
            return match.group(0).strip()
        return text.split('\n')[0].strip() if '\n' in text else text.strip()
    
    def _extract_topic_from_text(self, text: str) -> Optional[str]:
        """Извлекает тему из текста."""
        text_lower = text.lower()
        
        # Считаем вхождения ключевых слов для каждой темы
        topic_scores = {}
        
        for topic, keywords in self.topic_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            
            if score > 0:
                topic_scores[topic] = score
        
        if not topic_scores:
            return None
        
        # Возвращаем тему с наибольшим счетом
        return max(topic_scores.items(), key=lambda x: x[1])[0]


class KeywordExtractor(MetadataExtractor):
    """Экстрактор для извлечения ключевых слов."""
    
    def __init__(self, name: str = None, top_n: int = 10):
        """
        Инициализирует экстрактор ключевых слов.
        
        Args:
            name: Имя экстрактора
            top_n: Количество извлекаемых ключевых слов
        """
        super().__init__(name)
        self.top_n = top_n
    
    def extract(self, text: str, context: Dict[str, Any] = None) -> ExtractionResult:
        """
        Извлекает ключевые слова из текста.
        
        Args:
            text: Текст для анализа
            context: Контекстная информация
            
        Returns:
            Результат с ключевыми словами
        """
        cleaned_text = self._clean_text(text)
        
        # Получаем слова
        words = re.findall(r'\b\w+\b', cleaned_text)
        
        if not words:
            return ExtractionResult(
                {'key_terms': [], 'term_frequencies': {}},
                0.9,
                self.name
            )
        
        # Убираем стоп-слова
        stop_words_extractor = TextStatisticsExtractor()
        stop_words = stop_words_extractor.stop_words
        
        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if not filtered_words:
            # Если все слова оказались стоп-словами, используем все слова
            filtered_words = [w for w in words if len(w) > 2]
        
        # Считаем частоту
        word_freq = Counter(filtered_words)
        
        # Берем top_n наиболее частых слов
        top_words = word_freq.most_common(self.top_n)
        
        # Преобразуем в нужный формат
        key_terms = [word for word, _ in top_words]
        term_frequencies = {word: freq for word, freq in top_words}
        
        # Вычисляем уверенность на основе количества уникальных слов
        unique_words = len(set(filtered_words))
        confidence = min(0.95, unique_words / 20)  # Максимум 0.95
        
        metadata = {
            'key_terms': key_terms,
            'term_frequencies': term_frequencies,
            'unique_terms_count': unique_words
        }
        
        return ExtractionResult(metadata, confidence, self.name)

class CompositeMetadataExtractor(MetadataExtractor):
    """Композитный экстрактор, объединяющий несколько экстракторов."""
    
    def __init__(self, extractors: List[MetadataExtractor] = None, name: str = None):
        """
        Инициализирует композитный экстрактор.
        
        Args:
            extractors: Список экстракторов
            name: Имя экстрактора
        """
        super().__init__(name or "CompositeExtractor")
        
        if extractors:
            self.extractors = extractors
        else:
            # Экстракторы по умолчанию
            self.extractors = [
                FormulaPresenceExtractor("FormulaDetector"),
                TextStatisticsExtractor("TextStats"),
                TopicExtractor("TopicIdentifier", use_first_sentence=True),
                KeywordExtractor("KeywordExtractor", top_n=8)
            ]
        
        logger.info(f"Инициализирован CompositeMetadataExtractor с {len(self.extractors)} экстракторами")
    
    def extract(self, text: str, context: Dict[str, Any] = None) -> ExtractionResult:
        """
        Запускает все экстракторы и объединяет результаты.
        
        Args:
            text: Текст для анализа
            context: Контекстная информация
            
        Returns:
            Объединенный результат
        """
        all_results = []
        combined_metadata = {}
        
        for extractor in self.extractors:
            try:
                result = extractor.extract(text, context)
                all_results.append(result)
                
                # Объединяем метаданные
                combined_metadata.update(result.metadata)
                
                logger.debug(f"Экстрактор {extractor.name} завершил успешно")
            except Exception as e:
                logger.warning(f"Ошибка в экстракторе {extractor.name}: {e}")
        
        # Вычисляем среднюю уверенность
        if all_results:
            avg_confidence = sum(r.confidence for r in all_results) / len(all_results)
        else:
            avg_confidence = 0.5
        
        # Добавляем информацию о том, какие экстракторы сработали
        combined_metadata['extractors_used'] = [r.extractor_name for r in all_results]
        combined_metadata['extractor_count'] = len(all_results)
        
        return ExtractionResult(combined_metadata, avg_confidence, self.name)
    
    def add_extractor(self, extractor: MetadataExtractor):
        """Добавляет экстрактор в композит."""
        self.extractors.append(extractor)
        logger.info(f"Добавлен экстрактор: {extractor.name}")
    
    def remove_extractor(self, extractor_name: str):
        """Удаляет экстрактор по имени."""
        self.extractors = [e for e in self.extractors if e.name != extractor_name]
        logger.info(f"Удален экстрактор: {extractor_name}")


def extract_metadata(text: str, 
                     formulas: List[Formula] = None,
                     context: Dict[str, Any] = None,
                     extractor: MetadataExtractor = None) -> Dict[str, Any]:
    """
    Функция для извлечения метаданных.
    
    Args:
        text: Текст для анализа
        formulas: Список формул в тексте
        context: Дополнительный контекст
        extractor: Используемый экстрактор (если None, используется CompositeMetadataExtractor)
        
    Returns:
        Словарь с метаданными
    """
    # Подготавливаем контекст
    if context is None:
        context = {}
    
    if formulas is not None:
        context['formulas'] = formulas
    
    # Создаем экстрактор, если не передан
    if extractor is None:
        extractor = CompositeMetadataExtractor()
    
    # Извлекаем метаданные
    result = extractor.extract(text, context)
    
    # Добавляем уверенность в результат
    metadata = result.metadata
    metadata['extraction_confidence'] = round(result.confidence, 3)
    metadata['extractor_name'] = result.extractor_name
    
    return metadata


