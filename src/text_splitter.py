"""
Модуль для семантического разделения текста на логические блоки.

Предоставляет различные стратегии разбиения текста: по абзацам,
по семантической связности, по заголовкам и т.д.
"""

import re
import logging
import hashlib
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
import numpy as np

logger = logging.getLogger(__name__)


class SplitterType(str, Enum):
    """Типы стратегий разбиения текста."""
    PARAGRAPH = "paragraph"          # По абзацам
    SEMANTIC = "semantic"            # По семантической связности
    FIXED_SIZE = "fixed_size"        # По фиксированному размеру
    MIXED = "mixed"                  # Комбинированная стратегия
    SEMANTIC_EMBEDDING = "semantic_embedding" #Иерархичекая кластеризация с эмбедингами MiniLM


@dataclass
class SplitterConfig:
    """Конфигурация для разбиения текста."""
    
    splitter_type: SplitterType = SplitterType.PARAGRAPH
    """Тип стратегии разбиения."""
    
    min_chunk_size: int = 100
    """Минимальный размер чанка в символах."""
    
    max_chunk_size: int = 2000
    """Максимальный размер чанка в символах."""
    
    paragraph_separator: str = "\n\n"
    """Разделитель абзацев."""
    
    semantic_threshold: float = 0.3
    """Порог семантической схожести для объединения."""
    
    overlap_size: int = 50
    """Размер перекрытия между чанками (для fixed_size)."""
    
    preserve_headers: bool = True
    """Сохранять ли заголовки как отдельные чанки."""


@dataclass
class TextChunkInfo:
    """Информация о текстовом блоке."""
    
    text: str
    """Текст блока."""
    
    start_pos: int
    """Начальная позиция в исходном тексте."""
    
    end_pos: int
    """Конечная позиция в исходном тексте."""
    
    chunk_id: str
    """Уникальный идентификатор блока."""
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Метаданные блока."""


class TextSplitter(ABC):
    """Абстрактный базовый класс для стратегий разбиения текста."""
    
    def __init__(self, config: Optional[SplitterConfig] = None):
        """
        Инициализирует сплиттер.
        
        Args:
            config: Конфигурация разбиения
        """
        self.config = config or SplitterConfig()
        logger.info(f"Инициализирован {self.__class__.__name__}")
    
    @abstractmethod
    def split(self, text: str) -> List[TextChunkInfo]:
        """
        Разбивает текст на блоки.
        
        Args:
            text: Текст для разбиения
            
        Returns:
            Список текстовых блоков
        """
        pass
    
    def _generate_chunk_id(self, text: str, position: int) -> str:
        """
        Генерирует уникальный идентификатор для блока.
        
        Args:
            text: Текст блока
            position: Позиция блока
            
        Returns:
            Уникальный идентификатор
        """
        # Создаем хэш из текста и позиции
        content_hash = hashlib.md5(f"{text[:100]}_{position}".encode()).hexdigest()[:8]
        return f"chunk_{position:06d}_{content_hash}"
    
    def _validate_chunk_size(self, text: str) -> bool:
        """
        Проверяет, соответствует ли чанк ограничениям по размеру.
        
        Args:
            text: Текст чанка
            
        Returns:
            True если размер в допустимых пределах
        """
        length = len(text)
        return self.config.min_chunk_size <= length <= self.config.max_chunk_size


class ParagraphSplitter(TextSplitter):
    """Разбивает текст по абзацам."""
    
    def split(self, text: str) -> List[TextChunkInfo]:
        """
        Разбивает текст на абзацы.
        
        Args:
            text: Текст для разбиения
            
        Returns:
            Список абзацев
        """
        if not text:
            logger.warning("Получен пустой текст для разбиения")
            return []
        
        # Разделяем текст на абзацы
        paragraphs = self._split_into_paragraphs(text)
        
        chunks = []
        current_pos = 0
        
        for i, paragraph in enumerate(paragraphs):
            if not paragraph.strip():
                # Пропускаем пустые абзацы, но учитываем их длину для смещения позиции
                # (пустые строки тоже занимают место в исходном тексте)
                empty_len = len(paragraph) + len(self.config.paragraph_separator)
                current_pos += empty_len
                continue
            
            # Находим позицию абзаца в исходном тексте (поиск от current_pos)
            start_pos = text.find(paragraph, current_pos)
            if start_pos == -1:
                # Если не нашли (редкий случай), используем текущую позицию
                start_pos = current_pos
            
            end_pos = start_pos + len(paragraph)
            current_pos = end_pos + len(self.config.paragraph_separator)  # переходим за разделитель
            
            # Проверяем размер абзаца: если слишком большой – разбиваем
            if len(paragraph) > self.config.max_chunk_size:
                logger.debug(f"Абзац слишком большой ({len(paragraph)} символов), разбиваем дальше")
                sub_chunks = self._split_large_paragraph(paragraph, start_pos, i)
                chunks.extend(sub_chunks)
            else:
                # Создаём чанк для любого абзаца (даже очень короткого)
                chunk_id = self._generate_chunk_id(paragraph, i)
                
                chunk = TextChunkInfo(
                    text=paragraph,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    chunk_id=chunk_id,
                    metadata={
                        "splitter_type": "paragraph",
                        "paragraph_number": i,
                        "is_header": self._is_header(paragraph)
                    }
                )
                chunks.append(chunk)
        
        logger.info(f"Текст разбит на {len(chunks)} абзацев")
        return chunks
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Разделяет текст на абзацы."""
        # Используем указанный разделитель абзацев
        separator = self.config.paragraph_separator
        
        if separator == "\n\n":
            # Стандартное разделение по двойному переносу строки
            paragraphs = re.split(r'\n\s*\n', text)
        else:
            # Пользовательский разделитель
            paragraphs = text.split(separator)
        
        # Очищаем абзацы
        cleaned_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para:  # Пропускаем пустые
                cleaned_paragraphs.append(para)
        
        return cleaned_paragraphs
    
    
    def _is_header(self, text: str) -> bool:
        """Определяет, является ли текст заголовком."""
        # Заголовки обычно короткие и не заканчиваются точкой
        lines = text.split('\n')
        if len(lines) == 1:
            line = lines[0].strip()
            if (len(line) < 100 and 
                not line.endswith('.') and 
                not line.endswith('!') and 
                not line.endswith('?')):
                return True
        
        # Проверяем паттерны заголовков
        header_patterns = [
            r'^#+\s',           # Markdown заголовки
            r'^\d+\.\s',        # Нумерованные заголовки
            r'^[A-ZА-Я][^.!?]*:$',  # Заголовки с двоеточием
            r'^(Введение|Заключение|Глава|Раздел|Часть)\b',
        ]
        
        for pattern in header_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        
        return False

class SemanticSplitter(TextSplitter):
    """Разбивает текст по семантической связности."""
    
    def split(self, text: str) -> List[TextChunkInfo]:
        """
        Разбивает текст на семантически связные блоки.
        
        Args:
            text: Текст для разбиения
            
        Returns:
            Список семантических блоков
        """
        if not text:
            return []
        
        # Сначала разбиваем на абзацы
        paragraph_splitter = ParagraphSplitter(self.config)
        paragraphs = paragraph_splitter.split(text)
        
        if not paragraphs:
            return []
        
        # Объединяем абзацы по семантической связности
        chunks = []
        current_chunk_paragraphs = []
        current_start_pos = paragraphs[0].start_pos
        current_text = ""
        
        for i, paragraph in enumerate(paragraphs):
            paragraph_text = paragraph.text
            
            # Проверяем, нужно ли начинать новый чанк
            if (current_text and 
                (not self._are_semantically_related(current_text, paragraph_text) or
                 len(current_text + "\n\n" + paragraph_text) > self.config.max_chunk_size)):
                
                # Сохраняем текущий чанк
                chunk = self._create_chunk_from_paragraphs(
                    current_chunk_paragraphs, 
                    current_start_pos,
                    len(chunks)
                )
                chunks.append(chunk)
                
                # Начинаем новый чанк
                current_chunk_paragraphs = [paragraph]
                current_start_pos = paragraph.start_pos
                current_text = paragraph_text
            else:
                # Добавляем абзац к текущему чанку
                current_chunk_paragraphs.append(paragraph)
                if current_text:
                    current_text += "\n\n" + paragraph_text
                else:
                    current_text = paragraph_text
        
        # Добавляем последний чанк
        if current_chunk_paragraphs:
            chunk = self._create_chunk_from_paragraphs(
                current_chunk_paragraphs,
                current_start_pos,
                len(chunks)
            )
            chunks.append(chunk)
        
        logger.info(f"Текст разбит на {len(chunks)} семантических блоков")
        return chunks
    
    def _are_semantically_related(self, text1: str, text2: str) -> bool:
        """
        Проверяет, семантически связаны ли два текста.
        
        Args:
            text1: Первый текст
            text2: Второй текст
            
        Returns:
            True если тексты связаны
        """
        # Простая эвристика: проверяем общие ключевые слова и структуру
        
        # 1. Извлекаем ключевые слова (простые: слова длиннее 3 символов)
        words1 = set(re.findall(r'\b\w{4,}\b', text1.lower()))
        words2 = set(re.findall(r'\b\w{4,}\b', text2.lower()))
        
        # 2. Находим пересечение
        common_words = words1.intersection(words2)
        
        # 3. Вычисляем меру схожести
        if not words1 or not words2:
            return False
        
        similarity = len(common_words) / min(len(words1), len(words2))
        
        # 4. Проверяем порог
        return similarity >= self.config.semantic_threshold
    
    def _create_chunk_from_paragraphs(self, paragraphs: List[TextChunkInfo], 
                                     start_pos: int, chunk_num: int) -> TextChunkInfo:
        """Создает чанк из списка абзацев."""
        # Объединяем тексты абзацев
        chunk_text = "\n\n".join(p.text for p in paragraphs)
        
        # Вычисляем конечную позицию
        end_pos = paragraphs[-1].end_pos
        
        # Создаем метаданные
        metadata = {
            "splitter_type": "semantic",
            "paragraph_count": len(paragraphs),
            "contains_headers": any(p.metadata.get("is_header", False) for p in paragraphs),
            "paragraph_numbers": [p.metadata.get("paragraph_number", i) 
                                 for i, p in enumerate(paragraphs)]
        }
        
        chunk_id = self._generate_chunk_id(chunk_text, chunk_num)
        
        return TextChunkInfo(
            text=chunk_text,
            start_pos=start_pos,
            end_pos=end_pos,
            chunk_id=chunk_id,
            metadata=metadata
        )
    
class TextSplitterFactory:
    """Фабрика для создания сплиттеров."""
    
    @staticmethod
    def create_splitter(splitter_type: SplitterType = SplitterType.PARAGRAPH,
                       config: Optional[SplitterConfig] = None) -> TextSplitter:
        """
        Создает сплиттер указанного типа.
        
        Args:
            splitter_type: Тип сплиттера
            config: Конфигурация
            
        Returns:
            Экземпляр сплиттера
        """
        config = config or SplitterConfig()
        config.splitter_type = splitter_type
        
        if splitter_type == SplitterType.PARAGRAPH:
            return ParagraphSplitter(config)
        elif splitter_type == SplitterType.SEMANTIC:
            return SemanticSplitter(config)
        elif splitter_type == SplitterType.FIXED_SIZE:
            return FixedSizeSplitter(config)
        elif splitter_type == SplitterType.MIXED:
            return MixedSplitter(config)
        elif splitter_type == SplitterType.SEMANTIC_EMBEDDING:
            return SemanticEmbeddingSplitter(config)
        else:
            raise ValueError(f"Неизвестный тип сплиттера: {splitter_type}")



class FixedSizeSplitter(TextSplitter):
    """Разбивает текст на чанки фиксированного размера."""
    
    def split(self, text: str) -> List[TextChunkInfo]:
        chunks = []
        start = 0
        chunk_num = 0
        
        while start < len(text):
            # Определяем конец чанка
            end = min(start + self.config.max_chunk_size, len(text))
            
            # Если не конец текста, ищем границу предложения
            if end < len(text):
                # Ищем конец предложения
                sentence_end = self._find_sentence_boundary(text, end)
                if sentence_end > start + self.config.min_chunk_size:
                    end = sentence_end
            
            chunk_text = text[start:end].strip()
            
            if chunk_text and len(chunk_text) >= self.config.min_chunk_size:
                chunk_id = self._generate_chunk_id(chunk_text, chunk_num)
                
                chunk = TextChunkInfo(
                    text=chunk_text,
                    start_pos=start,
                    end_pos=end,
                    chunk_id=chunk_id,
                    metadata={
                        "splitter_type": "fixed_size",
                        "chunk_size": len(chunk_text),
                        "has_overlap": chunk_num > 0
                    }
                )
                chunks.append(chunk)
                chunk_num += 1
            
            # Учитываем перекрытие
            start = end - self.config.overlap_size if self.config.overlap_size > 0 else end
        
        logger.info(f"Текст разбит на {len(chunks)} блоков фиксированного размера")
        return chunks
    
    def _find_sentence_boundary(self, text: str, position: int) -> int:
        """Находит границу предложения."""
        # Ищем конец предложения
        for i in range(position, min(position + 100, len(text))):
            if text[i] in '.!?':
                # Проверяем, что это действительно конец предложения
                if i + 1 >= len(text) or text[i + 1].isspace():
                    return i + 1
        
        return position


class MixedSplitter(TextSplitter):
    """Комбинированная стратегия разбиения."""
    
    def split(self, text: str) -> List[TextChunkInfo]:
        # Сначала разбиваем на абзацы
        paragraph_splitter = ParagraphSplitter(self.config)
        paragraphs = paragraph_splitter.split(text)
        
        # Затем применяем семантическое объединение
        semantic_splitter = SemanticSplitter(self.config)
        
        # Преобразуем абзацы обратно в текст для семантического сплиттера
        paragraph_text = "\n\n".join(p.text for p in paragraphs)
        
        return semantic_splitter.split(paragraph_text)
    
class SemanticEmbeddingSplitter(TextSplitter):
    """Разбивает текст на семантические блоки с помощью эмбеддингов и иерархической кластеризации."""
    
    def __init__(self, config: SplitterConfig = None, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        super().__init__(config)
        self.model_name = model_name
        self.model = None   # ленивая загрузка
    
    def _get_model(self):
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
        return self.model
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Разбивает текст на предложения по .!? с последующим пробелом."""
        # Простое разбиение по .!? и пробелу – достаточно для большинства текстов
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def split(self, text: str) -> List[TextChunkInfo]:
        # 1. Разбиваем на предложения
        sentences = self._split_into_sentences(text)
        if len(sentences) <= 1:
            # Возвращаем один чанк
            chunk_id = self._generate_chunk_id(text, 0)
            return [TextChunkInfo(text=text, start_pos=0, end_pos=len(text), chunk_id=chunk_id, metadata={})]
        
        # 2. Строим эмбеддинги
        model = self._get_model()
        embeddings = model.encode(sentences, convert_to_numpy=True)
        
        # 3. Определяем количество кластеров (n_clusters)
        # Можно задать через конфиг или динамически
        n_clusters = getattr(self.config, 'target_chunks', None)
        if n_clusters is None:
            # По умолчанию: максимальное количество чанков ≈ число предложений / 5 (но не менее 2)
            n_clusters = max(2, len(sentences) // 5)
            n_clusters = min(n_clusters, 20)  # ограничим сверху
        
        # 4. Кластеризация с ограничением соседства
        n = len(sentences)
        connectivity = np.zeros((n, n))
        for i in range(n - 1):
            connectivity[i, i+1] = 1
            connectivity[i+1, i] = 1
        
        clustering = AgglomerativeClustering(
            n_clusters=min(n_clusters, n),
            metric='cosine',
            linkage='average',
            connectivity=connectivity
        )
        labels = clustering.fit_predict(embeddings)
        
        # 5. Группируем предложения по меткам (с учётом непрерывности)
        chunks_indices = []
        cur_label = labels[0]
        cur = [0]
        for i in range(1, n):
            if labels[i] != cur_label:
                chunks_indices.append(cur)
                cur = [i]
                cur_label = labels[i]
            else:
                cur.append(i)
        chunks_indices.append(cur)
        
        # 6. Создаём TextChunkInfo, склеивая предложения, и вычисляем позиции в исходном тексте
        chunks_info = []
        global_start = 0
        for idx, indices in enumerate(chunks_indices):
            chunk_text = ' '.join([sentences[i] for i in indices])
            # Находим позицию в исходном тексте (приблизительно, через поиск)
            start_pos = text.find(chunk_text, global_start)
            if start_pos == -1:
                # Fallback – ищем по-другому или используем глобальную позицию
                start_pos = global_start
            end_pos = start_pos + len(chunk_text)
            global_start = end_pos
            chunk_id = self._generate_chunk_id(chunk_text, idx)
            # Преобразуем метку кластера из numpy.int64 в обычный int
            cluster_label_val = labels[indices[0]] if indices else 0
            if hasattr(cluster_label_val, 'item'):
                cluster_label_val = cluster_label_val.item()

            metadata = {
                "splitter_type": "semantic_embedding",
                "num_sentences": len(indices),
                "cluster_label": int(cluster_label_val),
                "chunk_index": idx
            }
            chunks_info.append(TextChunkInfo(
                text=chunk_text,
                start_pos=start_pos,
                end_pos=end_pos,
                chunk_id=chunk_id,
                metadata=metadata
            ))
        
        return chunks_info


def split_text(text: str, 
               splitter_type: SplitterType = SplitterType.MIXED,
               **kwargs) -> List[TextChunkInfo]:
    """
    Функция для разбиения текста.
    
    Args:
        text: Текст для разбиения
        splitter_type: Тип сплиттера
        **kwargs: Аргументы для SplitterConfig
        
    Returns:
        Список текстовых блоков
    """
    config = SplitterConfig(**kwargs) if kwargs else SplitterConfig()
    splitter = TextSplitterFactory.create_splitter(splitter_type, config)
    return splitter.split(text)



