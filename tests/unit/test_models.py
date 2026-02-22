"""
Тесты для моделей данных из src/models.py
"""

import pytest
from datetime import datetime
from src.models import Formula, FormulaType, TextChunk, ProcessingStats, ProcessingResult


class TestFormula:
    """Тесты для класса Formula."""
    
    def test_formula_creation(self):
        """Тест создания объекта Formula."""
        formula = Formula(
            original="a^2 + b^2 = c^2",
            normalized="a**2 + b**2 = c**2",
            start_pos=10,
            end_pos=30,
            formula_type=FormulaType.PLAIN_TEXT
        )
        
        assert formula.original == "a^2 + b^2 = c^2"
        assert formula.normalized == "a**2 + b**2 = c**2"
        assert formula.start_pos == 10
        assert formula.end_pos == 30
        assert formula.formula_type == FormulaType.PLAIN_TEXT
    
    def test_formula_length(self):
        """Тест вычисления длины формулы."""
        formula = Formula(
            original="x = 5",
            normalized="x = 5",
            start_pos=0,
            end_pos=5,
            formula_type=FormulaType.PLAIN_TEXT
        )
        
        assert formula.length() == 5  # end_pos - start_pos
    
    def test_formula_str_representation(self):
        """Тест строкового представления формулы."""
        formula = Formula(
            original="E = mc^2",
            normalized="E = mc**2",
            start_pos=100,
            end_pos=108,
            formula_type=FormulaType.PLAIN_TEXT
        )
        
        # Проверяем, что __str__ работает без ошибок
        str_repr = str(formula)
        assert "Formula" in str_repr
        assert "type=plain_text" in str_repr or "type=FormulaType.PLAIN_TEXT" in str_repr
        assert "pos=100-108" in str_repr
    
    def test_formula_types(self):
        """Тест различных типов формул."""
        latex_inline = Formula(
            original="$E = mc^2$",
            normalized="E = mc**2",
            start_pos=0,
            end_pos=10,
            formula_type=FormulaType.LATEX_INLINE
        )
        
        latex_display = Formula(
            original="\\[\\int x^2 dx\\]",
            normalized="integral x**2 dx",
            start_pos=0,
            end_pos=15,
            formula_type=FormulaType.LATEX_DISPLAY
        )
        
        assert latex_inline.formula_type == FormulaType.LATEX_INLINE
        assert latex_display.formula_type == FormulaType.LATEX_DISPLAY
        assert latex_inline.formula_type != latex_display.formula_type
    
    def test_formula_edge_cases(self):
        """Тест граничных случаев для формулы."""
        # Формула нулевой длины (теоретически не должно быть, но проверим)
        formula = Formula(
            original="",
            normalized="",
            start_pos=0,
            end_pos=0,
            formula_type=FormulaType.PLAIN_TEXT
        )
        
        assert formula.length() == 0
        assert formula.original == ""
        
        # Формула с большими числами
        formula = Formula(
            original="x" * 100,
            normalized="y" * 100,
            start_pos=1000,
            end_pos=1100,
            formula_type=FormulaType.PLAIN_TEXT
        )
        
        assert formula.length() == 100
        assert len(formula.original) == 100


class TestTextChunk:
    """Тесты для класса TextChunk."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        # Создаем тестовые формулы
        self.formula1 = Formula(
            original="a + b",
            normalized="a + b",
            start_pos=0,
            end_pos=5,
            formula_type=FormulaType.PLAIN_TEXT
        )
        
        self.formula2 = Formula(
            original="$x^2$",
            normalized="x**2",
            start_pos=10,
            end_pos=15,
            formula_type=FormulaType.LATEX_INLINE
        )
    
    def test_text_chunk_creation(self):
        """Тест создания TextChunk."""
        chunk = TextChunk(
            id="chunk_001",
            sequence_number=1,
            original_text="Текст с формулой a + b",
            processed_text="Текст с формулой a + b",
            formulas=[self.formula1],
            metadata={"topic": "математика"}
        )
        
        assert chunk.id == "chunk_001"
        assert chunk.sequence_number == 1
        assert "Текст с формулой" in chunk.original_text
        assert len(chunk.formulas) == 1
        assert chunk.metadata["topic"] == "математика"
    
    def test_text_chunk_word_count(self):
        """Тест подсчета слов в чанке."""
        # Русский текст
        chunk_ru = TextChunk(
            id="chunk_ru",
            sequence_number=1,
            original_text="Привет мир, это тест",
            processed_text="Привет мир, это тест",
            formulas=[],
            metadata={}
        )
        
        # Английский текст
        chunk_en = TextChunk(
            id="chunk_en",
            sequence_number=2,
            original_text="Hello world this is test",
            processed_text="Hello world this is test",
            formulas=[],
            metadata={}
        )
        
        # Текст с формулами - split() разобьет на 6 частей: ['Формула:', 'a', '+', 'b', '=', 'c']
        chunk_with_formulas = TextChunk(
            id="chunk_formula",
            sequence_number=3,
            original_text="Формула: a + b = c",
            processed_text="Формула: a + b = c",
            formulas=[self.formula1],
            metadata={}
        )
        
        assert chunk_ru.word_count() == 4  # "Привет мир, это тест" → 4 слова
        assert chunk_en.word_count() == 5  # "Hello world this is test" → 5 слов
        assert chunk_with_formulas.word_count() == 6  # "Формула: a + b = c" → 6 токенов
    
    def test_word_count_with_punctuation(self):
        """Тест подсчета слов с разными знаками препинания."""
        # Текст с разными знаками препинания
        # ВАЖНО: .split() разбивает по пробелам, сохраняя знаки препинания
        test_cases = [
            ("Просто текст", 2),  # ['Просто', 'текст'] = 2
            ("Текст с запятой, вот так", 5),  # ['Текст', 'с', 'запятой,', 'вот', 'так'] = 5
            ("Точка. Второе предложение", 3),  # ['Точка.', 'Второе', 'предложение'] = 3
            ("a = b + c", 5),  # ['a', '=', 'b', '+', 'c'] = 5
            ("Много    пробелов     здесь", 3),  # Множественные пробелы игнорируются
            ("", 0),  # Пустая строка
            ("   ", 0),  # Только пробелы
        ]
        
        for i, (text, expected) in enumerate(test_cases):
            chunk = TextChunk(
                id=f"chunk_{i}",
                sequence_number=i,
                original_text=text,
                processed_text=text,
                formulas=[],
                metadata={}
            )
            
            actual = chunk.word_count()
            assert actual == expected, \
                f"Для текста '{text}': ожидалось {expected}, получено {actual}. " \
                f"Разбиение: {text.split()}"
    
    def test_word_count_edge_cases(self):
        """Тест граничных случаев для подсчета слов."""
        # Текст с табуляциями и новыми строками
        chunk = TextChunk(
            id="edge_chunk",
            sequence_number=99,
            original_text="Строка1\nСтрока2\tСтрока3",
            processed_text="Строка1\nСтрока2\tСтрока3",
            formulas=[],
            metadata={}
        )
        
        # \n и \t считаются пробелами для split(), так что будет 3 слова
        assert chunk.word_count() == 3
        
        # Текст только с числами и символами
        chunk2 = TextChunk(
            id="symbols_chunk",
            sequence_number=100,
            original_text="123 + 456 = 579",
            processed_text="123 + 456 = 579",
            formulas=[],
            metadata={}
        )
        
        # split() разобьет на ['123', '+', '456', '=', '579'] = 5 токенов
        assert chunk2.word_count() == 5
        
        # Смешанный текст
        chunk3 = TextChunk(
            id="mixed_chunk",
            sequence_number=101,
            original_text="Пи: π ≈ 3.14, формула: A=πr²",
            processed_text="Пи: π ≈ 3.14, формула: A=πr²",
            formulas=[],
            metadata={}
        )
        
        # ['Пи:', 'π', '≈', '3.14,', 'формула:', 'A=πr²'] = 6 токенов
        assert chunk3.word_count() == 6
    
    def test_has_formulas(self):
        """Тест проверки наличия формул в чанке."""
        chunk_with_formulas = TextChunk(
            id="with_formulas",
            sequence_number=1,
            original_text="Текст с формулами",
            processed_text="Текст с формулами",
            formulas=[self.formula1, self.formula2],
            metadata={}
        )
        
        chunk_without_formulas = TextChunk(
            id="without_formulas",
            sequence_number=2,
            original_text="Текст без формул",
            processed_text="Текст без формул",
            formulas=[],
            metadata={}
        )
        
        assert chunk_with_formulas.has_formulas() is True
        assert chunk_without_formulas.has_formulas() is False
        assert chunk_with_formulas.has_formulas() != chunk_without_formulas.has_formulas()
    
    def test_text_chunk_str_representation(self):
        """Тест строкового представления чанка."""
        chunk = TextChunk(
            id="test_chunk_123",
            sequence_number=5,
            original_text="Длинный текст который будет обрезан при выводе" * 10,
            processed_text="Длинный текст который будет обрезан при выводе" * 10,
            formulas=[self.formula1],
            metadata={"complexity": "high"}
        )
        
        str_repr = str(chunk)
        
        # Проверяем, что строка содержит основные поля
        assert "TextChunk" in str_repr
        assert "test_chunk_123" in str_repr
        assert "seq=5" in str_repr
        assert "..." in str_repr  # Должен быть обрезанный текст
        
        # Проверяем обрезание длинного текста
        assert len(str_repr) < 200  # Строковое представление не должно быть очень длинным
    
    def test_text_chunk_with_empty_text(self):
        """Тест чанка с пустым текстом."""
        chunk = TextChunk(
            id="empty_chunk",
            sequence_number=0,
            original_text="",
            processed_text="",
            formulas=[],
            metadata={}
        )
        
        assert chunk.word_count() == 0
        assert chunk.has_formulas() is False
        assert chunk.original_text == ""


class TestProcessingStats:
    """Тесты для класса ProcessingStats."""
    
    def test_stats_creation(self):
        """Тест создания статистики."""
        stats = ProcessingStats(
            total_chunks=15,
            total_formulas=8,
            processing_time_seconds=2.5,
            input_file_size_bytes=10240
        )
        
        assert stats.total_chunks == 15
        assert stats.total_formulas == 8
        assert stats.processing_time_seconds == 2.5
        assert stats.input_file_size_bytes == 10240
    
    def test_stats_to_dict(self):
        """Тест преобразования статистики в словарь."""
        stats = ProcessingStats(
            total_chunks=10,
            total_formulas=5,
            processing_time_seconds=1.234567,
            input_file_size_bytes=5000
        )
        
        stats_dict = stats.to_dict()
        
        assert isinstance(stats_dict, dict)
        assert stats_dict["total_chunks"] == 10
        assert stats_dict["total_formulas"] == 5
        assert stats_dict["processing_time_seconds"] == 1.235  # Округление до 3 знаков
        assert stats_dict["input_file_size_bytes"] == 5000
    
    def test_stats_default_values(self):
        """Тест значений по умолчанию."""
        stats = ProcessingStats()
        
        assert stats.total_chunks == 0
        assert stats.total_formulas == 0
        assert stats.processing_time_seconds == 0.0
        assert stats.input_file_size_bytes == 0


class TestProcessingResult:
    """Тесты для класса ProcessingResult."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        # Создаем тестовые чанки
        self.chunk1 = TextChunk(
            id="chunk_001",
            sequence_number=0,
            original_text="Первый блок",
            processed_text="Первый блок",
            formulas=[],
            metadata={"words": 2}
        )
        
        self.chunk2 = TextChunk(
            id="chunk_002",
            sequence_number=1,
            original_text="Второй блок с формулой E=mc^2",
            processed_text="Второй блок с формулой E=mc**2",
            formulas=[
                Formula(
                    original="E=mc^2",
                    normalized="E=mc**2",
                    start_pos=20,
                    end_pos=26,
                    formula_type=FormulaType.PLAIN_TEXT
                )
            ],
            metadata={"words": 5, "has_formula": True}
        )
        
        self.stats = ProcessingStats(
            total_chunks=2,
            total_formulas=1,
            processing_time_seconds=0.5,
            input_file_size_bytes=1000
        )
    
    def test_result_creation(self):
        """Тест создания результата обработки."""
        result = ProcessingResult(
            chunks=[self.chunk1, self.chunk2],
            statistics=self.stats,
            source_file="lecture.pdf"
        )
        
        assert len(result.chunks) == 2
        assert result.statistics.total_chunks == 2
        assert result.source_file == "lecture.pdf"
        assert result.process_id is not None  # Должен сгенерироваться автоматически
        assert isinstance(result.processed_at, datetime)
    
    def test_result_to_dict(self):
        """Тест преобразования результата в словарь для JSON."""
        result = ProcessingResult(
            chunks=[self.chunk1, self.chunk2],
            statistics=self.stats,
            source_file="test.pdf"
        )
        
        result_dict = result.to_dict()
        
        # Проверяем структуру
        assert "process_id" in result_dict
        assert "source_file" in result_dict
        assert "processed_at" in result_dict
        assert "statistics" in result_dict
        assert "chunks" in result_dict
        
        # Проверяем содержимое
        assert result_dict["source_file"] == "test.pdf"
        assert result_dict["statistics"]["total_chunks"] == 2
        assert len(result_dict["chunks"]) == 2
        
        # Проверяем сериализацию формул
        chunk_with_formula = result_dict["chunks"][1]
        assert len(chunk_with_formula["formulas"]) == 1
        formula_dict = chunk_with_formula["formulas"][0]
        assert formula_dict["original"] == "E=mc^2"
        assert formula_dict["type"] == "plain_text"
    
    def test_result_str_representation(self):
        """Тест строкового представления результата."""
        result = ProcessingResult(
            chunks=[self.chunk1],
            statistics=ProcessingStats(total_chunks=1, total_formulas=0),
            source_file="big_lecture.pdf"
        )
        
        str_repr = str(result)
        
        assert "ProcessingResult" in str_repr
        assert "big_lecture.pdf" in str_repr
        assert "chunks=1" in str_repr
        assert "formulas=0" in str_repr
    
    def test_result_with_empty_chunks(self):
        """Тест результата с пустым списком чанков."""
        result = ProcessingResult(
            chunks=[],
            statistics=ProcessingStats(),
            source_file="empty.pdf"
        )
        
        assert len(result.chunks) == 0
        result_dict = result.to_dict()
        assert len(result_dict["chunks"]) == 0