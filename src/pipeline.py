"""
Основной модуль конвейера обработки лекций.

Объединяет все компоненты системы в единый конвейер обработки:
загрузка → нормализация → поиск формул → разбиение → метаданные → вывод.
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import re
from dataclasses import asdict

from src.data_models import Formula, TextChunk, ProcessingResult, ProcessingStats
from src.file_loader import FileLoaderFactory, load_file
from src.text_normalizer import TextNormalizer
from src.formula_extractor import FormulaExtractor, FormulaDetectionResult
from src.text_splitter import split_text, SplitterType, TextChunkInfo
from src.metadata_extractor import extract_metadata
from src.text_cleaner import LectureTextCleaner
from src.file_loader import FileLoaderFactory, AudioLoader, VideoLoader, load_file
from src.data_models import BlockType

logger = logging.getLogger(__name__)


class LectureProcessingPipeline:
    """Основной конвейер обработки лекций."""
    
    def __init__(self, 
                 detect_plain_text_formulas: bool = True,
                 splitter_type: SplitterType = SplitterType.MIXED,
                 min_chunk_size: int = 100,
                 max_chunk_size: int = 50000,
                 preserve_original_text: bool = True,
                ):
        """
        Инициализирует конвейер обработки.
        
        Args:
            detect_plain_text_formulas: Обнаруживать ли plain-text формулы
            splitter_type: Тип разбиения текста
            min_chunk_size: Минимальный размер чанка
            max_chunk_size: Максимальный размер чанка
            preserve_original_text: Сохранять ли оригинальный текст в результатах
        """
        self.detect_plain_text_formulas = detect_plain_text_formulas
        self.splitter_type = splitter_type
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.preserve_original_text = preserve_original_text
        
        # Инициализируем компоненты
        self.text_normalizer = TextNormalizer(preserve_formula_placeholders=True)
        self.formula_extractor = FormulaExtractor(
            detect_plain_text=detect_plain_text_formulas
        )
        
        self.text_cleaner = LectureTextCleaner()  

        logger.info(f"Инициализирован конвейер обработки (splitter: {splitter_type})")
    
    def process(self, file_path: str) -> ProcessingResult:
        """
        Основной метод обработки файла.
        
        Args:
            file_path: Путь к файлу для обработки
            
        Returns:
            Результат обработки
            
        Raises:
            FileNotFoundError: Если файл не существует
            ValueError: Если файл не поддерживается или поврежден
        """
        start_time = time.time()
        
        try:
            logger.info(f"Начало обработки файла: {file_path}")
     
            # Шаг 1: Загрузка файла
            logger.debug("Шаг 1: Загрузка файла")
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.mp3':
                loader = AudioLoader(model_size="small", device="cpu", compute_type="int8")
            elif ext == '.mp4':
                loader = VideoLoader(model_size="small", device="cpu", compute_type="int8")
            else:
                loader = FileLoaderFactory.get_loader(file_path)
            raw_content = loader.load(file_path)
            file_metadata = loader.get_metadata()
            if ext == '.docx':
                from src.markdown_cleaner import MarkdownCleaner
                cleaner = MarkdownCleaner()
                raw_content = cleaner.clean(raw_content)
                logger.debug("Markdown-разметка удалена из DOCX")
            
            # Шаг 2: Нормализация текста
            logger.debug("Шаг 2: Нормализация текста")
            normalized_content, normalization_stats = self._normalize_text(raw_content)
            #Шаг 2.1: Очистка текста (для аудио/видео)
            if ext in ('.mp3', '.mp4'):
                logger.debug("Шаг 2.5: Очистка текста от нерелевантных фрагментов")
                normalized_content = self.text_cleaner.clean(normalized_content)


            # Шаг 3.1: Поиск и обработка формул (только для текстовых файлов, не для аудио/видео)
            if ext in ('.mp3', '.mp4'):
                logger.info("Для аудио/видео поиск формул пропускаем")
                # Создаём пустой результат: текст без изменений, список формул пуст
                formula_result = FormulaDetectionResult(
                    formulas=[],
                    text_with_placeholders=normalized_content,
                    placeholder_to_formula={},
                    detection_stats={"skipped": True}
                )
            else:
                logger.debug("Шаг 3.1: Поиск формул")
                formula_result = self._extract_formulas(normalized_content)
            
            # Шаг 4: Разбиение на блоки
            logger.debug("Шаг 4: Разбиение на блоки")
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ('.mp3', '.mp4'):
                # Для аудио/видео используем семантический эмбеддинг-сплиттер
                active_splitter = SplitterType.SEMANTIC_EMBEDDING
            else:
                # Для текстовых файлов используем MIXED
                active_splitter = self.splitter_type  
            chunks_info = self._split_text(formula_result.text_with_placeholders, splitter_type=active_splitter)
            
            # Шаг 5: Создание текстовых блоков с метаданными
            logger.debug("Шаг 5: Создание блоков с метаданными")
            text_chunks = self._create_text_chunks(
                chunks_info, 
                formula_result, 
                normalized_content
            )
            
            # Шаг 6: Сбор статистики
            logger.debug("Шаг 6: Сбор статистики")
            stats = self._collect_statistics(
                file_path=file_path,
                file_metadata=file_metadata,
                normalization_stats=normalization_stats,
                formula_result=formula_result,
                chunks_count=len(text_chunks),
                start_time=start_time
            )
            
            # Шаг 7: Создание финального результата
            result = ProcessingResult(
                chunks=text_chunks,
                statistics=stats,
                source_file=os.path.basename(file_path)
            )
            
            logger.info(f"Обработка завершена успешно. "
                    f"Блоков: {len(text_chunks)}, "
                    f"Формул: {stats.total_formulas}, "
                    f"Время: {stats.processing_time_seconds:.2f}с")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при обработке файла {file_path}: {e}")
            raise
    
    def _load_file(self, file_path: str) -> tuple[str, Dict[str, Any]]:
        """Загружает файл и возвращает его содержимое и метаданные."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        content, metadata = load_file(file_path)
        logger.debug(f"Файл загружен: {len(content)} символов, "
                    f"тип: {metadata.get('file_type', 'unknown')}")
        
        return content, metadata
    
    def _normalize_text(self, text: str) -> tuple[str, Dict[str, Any]]:
        """Нормализует текст и возвращает статистику."""
        normalized, stats = self.text_normalizer.normalize(text)
        
        logger.debug(f"Текст нормализован: {len(text)} -> {len(normalized)} символов")
        
        return normalized, stats.to_dict()
    
    def _extract_formulas(self, text: str) -> FormulaDetectionResult:
        """Извлекает формулы из текста."""
        result = self.formula_extractor.extract(text)
        
        logger.debug(f"Найдено формул: {len(result.formulas)} "
                    f"(LaTeX: {result.detection_stats.get('latex_inline', 0) + result.detection_stats.get('latex_display', 0)}, "
                    f"plain: {result.detection_stats.get('plain_text', 0)})")
        
        return result

    def _split_text(self, text: str, splitter_type: SplitterType = None) -> List[TextChunkInfo]:
        """Разбивает текст на блоки с возможностью временно переопределить тип сплиттера."""
        if splitter_type is None:
            splitter_type = self.splitter_type
        chunks = split_text(
            text,
            splitter_type=splitter_type,
            min_chunk_size=self.min_chunk_size,
            max_chunk_size=self.max_chunk_size
        )
        return chunks
    
    def _create_text_chunks(self, 
                        chunks_info: List[TextChunkInfo],
                        formula_result: FormulaDetectionResult,
                        original_normalized_text: str) -> List[TextChunk]:
        """
        Создаёт объекты TextChunk с метаданными.
        """
        text_chunks = []
        
        for i, chunk_info in enumerate(chunks_info):
            # Восстанавливаем формулы из плейсхолдеров
            restored_text = self.formula_extractor.restore_formulas(
                chunk_info.text, formula_result.placeholder_to_formula
            )
            # Убираем возможные оставшиеся плейсхолдеры (если восстановление не сработало)
            restored_text = re.sub(r'\[\[FORMULA_\d+_\d+\]\]', '', restored_text)
            
            block_type = BlockType.TEXT
            
            # Находим формулы, попадающие в этот чанк (по позициям)
            chunk_formulas = []
            for formula in formula_result.formulas:
                if chunk_info.start_pos <= formula.start_pos <= chunk_info.end_pos:
                    chunk_formulas.append(formula)
            
            # Извлекаем метаданные
            metadata = extract_metadata(
                restored_text,
                formulas=chunk_formulas,
                context={'parent_metadata': chunk_info.metadata}
            )
            combined_metadata = {**chunk_info.metadata, **metadata}
            
            original_chunk_text = restored_text
            
            text_chunk = TextChunk(
                id=chunk_info.chunk_id,
                sequence_number=i,
                original_text=original_chunk_text,
                processed_text=restored_text,
                formulas=chunk_formulas,
                metadata=combined_metadata,
                block_type=block_type
            )
            text_chunks.append(text_chunk)
        
        return text_chunks
    
    def _collect_statistics(self,
                           file_path: str,
                           file_metadata: Dict[str, Any],
                           normalization_stats: Dict[str, Any],
                           formula_result: FormulaDetectionResult,
                           chunks_count: int,
                           start_time: float) -> ProcessingStats:
        """Собирает статистику обработки."""
        processing_time = time.time() - start_time
        file_extension = os.path.splitext(file_path)[1].lower()

        stats = ProcessingStats(
            total_chunks=chunks_count,
            total_formulas=len(formula_result.formulas),
            processing_time_seconds=processing_time,
            input_file_size_bytes=file_metadata.get('file_size', 0),
            file_extension=file_extension
        )
        
        # Добавляем дополнительную статистику
        stats_dict = asdict(stats)
        stats_dict.update({
            'normalization_stats': normalization_stats,
            'formula_detection_stats': formula_result.detection_stats,
            'file_metadata': {
                k: v for k, v in file_metadata.items() 
                if not isinstance(v, (bytes, bytearray))
            }
        })
        
        return stats 
    
def save_result_to_json(result: ProcessingResult, output_path: str) -> None:
    """
    Сохраняет результат обработки в JSON файл.
    
    Args:
        result: Результат обработки
        output_path: Путь для сохранения файла
    """
    result_dict = result.to_dict()
    
    # Форматируем JSON для читаемости
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2, default=str)
    
    logger.info(f"Результат сохранен в {output_path}")


def process_file(file_path: str, 
                 output_path: Optional[str] = None,
                 **pipeline_kwargs) -> ProcessingResult:
    """
    Удобная функция для обработки файла.
    
    Args:
        file_path: Путь к входному файлу
        output_path: Путь для сохранения результата (если None, не сохраняется)
        **pipeline_kwargs: Аргументы для LectureProcessingPipeline
        
    Returns:
        Результат обработки
    """
    # Создаем конвейер
    pipeline = LectureProcessingPipeline(**pipeline_kwargs)
    
    # Обрабатываем файл
    result = pipeline.process(file_path)
    
    # Сохраняем результат, если указан output_path
    if output_path:
        save_result_to_json(result, output_path)
    
    return result


class PipelineConfig:
    """Конфигурация конвейера обработки."""
    
    def __init__(self, 
                 detect_plain_text_formulas: bool = True,
                 splitter_type: SplitterType = SplitterType.SEMANTIC_EMBEDDING,
                 min_chunk_size: int = 100,
                 max_chunk_size: int = 50000,
                 output_format: str = 'json'):
        """
        Инициализирует конфигурацию.
        
        Args:
            detect_plain_text_formulas: Обнаруживать ли plain-text формулы
            splitter_type: Тип разбиения текста
            min_chunk_size: Минимальный размер чанка
            max_chunk_size: Максимальный размер чанка
            output_format: Формат вывода ('json' или 'dict')
        """
        self.detect_plain_text_formulas = detect_plain_text_formulas
        self.splitter_type = splitter_type
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.output_format = output_format
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует конфигурацию в словарь."""
        return {
            'detect_plain_text_formulas': self.detect_plain_text_formulas,
            'splitter_type': self.splitter_type.value,
            'min_chunk_size': self.min_chunk_size,
            'max_chunk_size': self.max_chunk_size,
            'output_format': self.output_format
        }


