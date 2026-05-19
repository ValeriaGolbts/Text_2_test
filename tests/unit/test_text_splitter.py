"""
Тесты для модуля разбиения текста на блоки.
"""

import pytest
from src.text_splitter import (
    ParagraphSplitter,
    SemanticSplitter,
    FixedSizeSplitter,
    MixedSplitter,
    TextSplitterFactory,
    SplitterType,
    SplitterConfig,
    split_text
)


class TestParagraphSplitter:
    """Тесты для ParagraphSplitter."""
    
    def setup_method(self):
        self.splitter = ParagraphSplitter()
    
    def test_split_simple_paragraphs(self):
        text = "Первый абзац.\n\nВторой абзац.\n\nТретий абзац."
        chunks = self.splitter.split(text)
        assert len(chunks) == 3
        assert "Первый абзац." in chunks[0].text
        assert "Второй абзац." in chunks[1].text
        assert "Третий абзац." in chunks[2].text
    
    def test_split_with_extra_newlines(self):
        text = "Первый абзац.\n\n\nВторой абзац.\n\n\n\nТретий абзац."
        chunks = self.splitter.split(text)
        # Должно быть 3 абзаца, лишние переносы игнорируются
        assert len(chunks) == 3
    
    def test_split_empty_text(self):
        chunks = self.splitter.split("")
        assert chunks == []
    
    def test_split_without_double_newline(self):
        text = "Один абзац.\nДругой абзац.\nТретий абзац."
        # Если нет двойных переносов, должен быть один чанк
        chunks = self.splitter.split(text)
        assert len(chunks) == 1
    
    def test_paragraph_too_large(self, monkeypatch):
        # Установим маленький max_chunk_size для теста
        config = SplitterConfig(max_chunk_size=50)
        splitter = ParagraphSplitter(config)
        text = "Это предложение длинное. " * 20  # явно больше 50
        chunks = splitter.split(text)
        # Должен разбить на несколько чанков
        assert len(chunks) > 1


class TestSemanticSplitter:
    """Тесты для SemanticSplitter."""
    
    def setup_method(self):
        self.splitter = SemanticSplitter()
    
    def test_semantic_merge(self):
        # Два абзаца на одну тему должны объединиться
        text = "Теорема Пифагора: a² + b² = c².\n\nЭто важное утверждение в геометрии."
        chunks = self.splitter.split(text)
        # Ожидаем один чанк, так как темы связаны (ключевые слова)
        assert len(chunks) == 1
    
    def test_different_topics(self):
        text = "Обсуждаем математику.\n\nТеперь поговорим о физике."
        chunks = self.splitter.split(text)
        # Может объединить или нет – зависит от эвристики. Проверим, что хотя бы не падает.
        assert isinstance(chunks, list)
        # Можно проверить, что общее количество чанков меньше числа абзацев, если объединились
        paragraph_splitter = ParagraphSplitter()
        paras = paragraph_splitter.split(text)
        assert len(chunks) <= len(paras)


class TestFixedSizeSplitter:
    """Тесты для FixedSizeSplitter."""
    
    def setup_method(self):
        config = SplitterConfig(max_chunk_size=50, overlap_size=10)
        self.splitter = FixedSizeSplitter(config)
    
    def test_fixed_size_splitting(self):
        text = "слово " * 100
        chunks = self.splitter.split(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text) <= 50
    
    def test_overlap(self):
        text = "a " * 100
        chunks = self.splitter.split(text)
        # Проверим, что есть перекрытие: текст первого чанка должен частично совпадать со вторым
        if len(chunks) >= 2:
            overlap_expected = 10
            # Не строго, но идея
            assert chunks[0].end_pos - chunks[1].start_pos > 0


class TestSplitterFactory:
    """Тесты фабрики сплиттеров."""
    
    def test_create_paragraph_splitter(self):
        splitter = TextSplitterFactory.create_splitter(SplitterType.PARAGRAPH)
        from src.text_splitter import ParagraphSplitter
        assert isinstance(splitter, ParagraphSplitter)
    
    def test_create_semantic_splitter(self):
        splitter = TextSplitterFactory.create_splitter(SplitterType.SEMANTIC)
        from src.text_splitter import SemanticSplitter
        assert isinstance(splitter, SemanticSplitter)
    
    def test_create_fixed_size_splitter(self):
        splitter = TextSplitterFactory.create_splitter(SplitterType.FIXED_SIZE)
        from src.text_splitter import FixedSizeSplitter
        assert isinstance(splitter, FixedSizeSplitter)
    
    def test_create_mixed_splitter(self):
        splitter = TextSplitterFactory.create_splitter(SplitterType.MIXED)
        from src.text_splitter import MixedSplitter
        assert isinstance(splitter, MixedSplitter)
    
    def test_create_with_config(self):
        config = SplitterConfig(min_chunk_size=200, max_chunk_size=500)
        splitter = TextSplitterFactory.create_splitter(SplitterType.PARAGRAPH, config)
        assert splitter.config.min_chunk_size == 200
        assert splitter.config.max_chunk_size == 500


def test_split_text_function():
    """Тест функции-обертки split_text."""
    text = "Абзац 1.\n\nАбзац 2.\n\nАбзац 3."
    chunks = split_text(text, splitter_type=SplitterType.PARAGRAPH)
    assert len(chunks) == 3
    assert all(hasattr(c, 'chunk_id') for c in chunks)