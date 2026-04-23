"""
Модуль с моделями данных 

Определяет структуры данных, которые передаются между компонентами конвейера.
"""
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class BlockType(str, Enum):
    """Тип текстового блока."""
    TEXT = "text"
    CODE = "code"
    FORMULA = "formula"      
    MIXED = "mixed"           # если в блоке смесь

class FormulaType(str, Enum):
    """Типы математических формул."""
    LATEX_INLINE = "latex_inline"      # Формулы в $...$
    LATEX_DISPLAY = "latex_display"    # Формулы в \[...\]
    PLAIN_TEXT = "plain_text"          # Текстовые формулы (a^2 + b^2 = c^2)
    UNKNOWN = "unknown"                # Неопределенный тип


@dataclass
class Formula:
    """Класс, представляющий математическую формулу."""
    
    original: str
    """Исходное представление формулы в тексте."""
    
    normalized: str
    """Нормализованное представление формулы."""
    
    start_pos: int
    """Начальная позиция формулы в исходном тексте (индекс символа)."""
    
    end_pos: int
    """Конечная позиция формулы в исходном тексте (индекс символа)."""
    
    formula_type: FormulaType
    """Тип формулы."""
    
    def length(self) -> int:
        """Возвращает длину формулы в символах."""
        return self.end_pos - self.start_pos
    
    def __str__(self) -> str:
        return f"Formula(type={self.formula_type}, pos={self.start_pos}-{self.end_pos})" 
    

@dataclass
class TextChunk:
    """Класс, представляющий текстовый блок (чанк)."""

    id: str
    """Уникальный идентификатор блока."""

    sequence_number: int
    """Порядковый номер блока в документе (начиная с 0)."""

    original_text: str
    """Исходный текст блока (как в документе)."""

    processed_text: str
    """Обработанный текст блока (после нормализации и замены формул)."""

    formulas: List[Formula] = field(default_factory=list)
    """Список формул, найденных в этом блоке."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Метаданные блока (тема, ключевые слова и т.д.)."""
    block_type: BlockType = BlockType.TEXT
    """Тип блока (текст, код, формула)."""

    def word_count(self) -> int:
        """Возвращает приблизительное количество слов в блоке."""
        # Простая реализация - разделение по пробелам
        return len(self.processed_text.split())

    def has_formulas(self) -> bool:
        """Проверяет, содержит ли блок формулы."""
        return len(self.formulas) > 0

    def __str__(self) -> str:
        preview = self.processed_text[:50] + "..." if len(self.processed_text) > 50 else self.processed_text
        return f"TextChunk(id={self.id}, seq={self.sequence_number}, words={self.word_count()}, text='{preview}')"


@dataclass
class ProcessingStats:
    """Статистика обработки документа."""
    
    total_chunks: int = 0
    """Общее количество текстовых блоков."""
    
    total_formulas: int = 0
    """Общее количество найденных формул."""
    
    processing_time_seconds: float = 0.0
    """Время обработки в секундах."""
    
    input_file_size_bytes: int = 0
    """Размер исходного файла в байтах."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует статистику в словарь."""
        return {
            "total_chunks": self.total_chunks,
            "total_formulas": self.total_formulas,
            "processing_time_seconds": round(self.processing_time_seconds, 3),
            "input_file_size_bytes": self.input_file_size_bytes
        }


@dataclass
class ProcessingResult:
    """Результат обработки документа."""
    
    chunks: List[TextChunk]
    """Список текстовых блоков."""
    
    statistics: ProcessingStats
    """Статистика обработки."""
    
    source_file: str
    """Имя исходного файла."""
    
    processed_at: datetime = field(default_factory=datetime.now)
    """Время завершения обработки."""
    
    process_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Уникальный идентификатор процесса обработки."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует результат в словарь для сериализации в JSON."""
        return {
            "process_id": self.process_id,
            "source_file": self.source_file,
            "processed_at": self.processed_at.isoformat(),
            "statistics": self.statistics.to_dict(),
            "chunks": [
                {
                    "id": chunk.id,
                    "sequence": chunk.sequence_number,
                    "original_text": chunk.original_text,
                    "processed_text": chunk.processed_text,
                    "block_type": chunk.block_type.value,
                    "formulas": [
                        {
                            "original": formula.original,
                            "normalized": formula.normalized,
                            "type": formula.formula_type.value,
                            "position": {"start": formula.start_pos, "end": formula.end_pos}
                        }
                        for formula in chunk.formulas
                    ],
                    "metadata": chunk.metadata
                }
                for chunk in self.chunks
            ]
        }
    
    def __str__(self) -> str:
        return (f"ProcessingResult(file='{self.source_file}', "
                f"chunks={len(self.chunks)}, formulas={self.statistics.total_formulas})")