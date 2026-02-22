"""
Тесты для модуля нормализации текста.
"""

import re
import pytest
from src.text_normalizer import TextNormalizer, normalize_text, normalize_whitespace


class TestTextNormalizer:
    """Тесты для класса TextNormalizer."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.normalizer = TextNormalizer()
        print("Инициализирован TextNormalizer")
    
    def test_normalize_basic_text(self):
        """Тест базовой нормализации текста."""
        # Исходный текст с разными проблемами
        input_text = (
            "  Текст  с   лишними   пробелами.\n"
            "И  переносами\r\n строк.\r"
            "И табуляциями\tвот так."
        )
        
        normalized, stats = self.normalizer.normalize(input_text)
        
        # Проверяем что текст не пустой
        assert len(normalized) > 0
        
        # Проверяем что убраны лишние пробелы
        assert "   " not in normalized  # Не должно быть тройных пробелов
        assert "  " not in normalized   # Не должно быть двойных пробелов в середине
        
        # Проверяем что нормализованы переносы строк
        assert "\r\n" not in normalized  # Windows-style
        assert "\r" not in normalized    # Mac-style
        
        # Проверяем статистику
        assert stats.original_length == len(input_text)
        assert stats.normalized_length == len(normalized)
        assert stats.normalized_length <= stats.original_length
        
        print(f"✓ test_normalize_basic_text: {stats.original_length} -> {stats.normalized_length} символов")
    
    def test_normalize_with_special_characters(self):
        """Тест нормализации текста со специальными символами."""
        # Текст с управляющими символами и BOM
        input_text = "\ufeffТекст с BOM\x00и\x01управляющими\x02символами\x0b\x0c"
        
        normalized, stats = self.normalizer.normalize(input_text)
        
        # Проверяем что BOM удален
        assert "\ufeff" not in normalized
        
        # Проверяем что управляющие символы удалены
        assert "\x00" not in normalized
        assert "\x01" not in normalized
        assert "\x02" not in normalized
        assert "\x0b" not in normalized
        assert "\x0c" not in normalized
        
        # Проверяем что обычный текст сохранен
        assert "Текст с BOM" in normalized
        assert "управляющими символами" in normalized
        
        print(f"✓ test_normalize_with_special_characters: удалено {stats.special_chars_removed} спецсимволов")
    
    def test_normalize_preserve_formula_placeholders(self):
        """Тест что плейсхолдеры формул сохраняются при нормализации."""
        normalizer_with_placeholders = TextNormalizer(preserve_formula_placeholders=True)
        
        input_text = "Текст с [[FORMULA_1]] и [[FORMULA_2]] формулами"
        
        normalized, _ = normalizer_with_placeholders.normalize(input_text)
        
        # Проверяем что плейсхолдеры сохранились
        assert "[[FORMULA_1]]" in normalized
        assert "[[FORMULA_2]]" in normalized
        assert "Текст с" in normalized
        assert "формулами" in normalized
        
        print("✓ test_normalize_preserve_formula_placeholders: плейсхолдеры сохранены")
    
    def test_normalize_linebreaks(self):
        """Тест нормализации переносов строк."""
        # Смешанные переносы строк
        input_text = "Строка1\r\nСтрока2\rСтрока3\nСтрока4\n\nСтрока5"
        
        normalized, _ = self.normalizer.normalize(input_text)
        
        # Должны остаться только \n
        assert "\r\n" not in normalized
        assert "\r" not in normalized
        assert "\n" in normalized
        
        # Проверяем структуру
        lines = normalized.split('\n')
        assert len(lines) >= 5  # Должно быть минимум 5 строк
        
        # Проверяем что убраны пустые строки в начале/конце
        assert normalized[0] != '\n'  # Не начинается с переноса
        assert normalized[-1] != '\n'  # Не заканчивается переносом
        
        print(f"✓ test_normalize_linebreaks: {len(lines)} строк после нормализации")
    
    def test_normalize_whitespace_only(self):
        """Тест метода normalize_whitespace_only."""
        input_text = "  Текст  с\t\tтабуляциями  \n\nи  пробелами  "
        
        normalized = self.normalizer.normalize_whitespace_only(input_text)
        
        # Проверяем что убраны лишние пробелы
        assert normalized.startswith("Текст")  # Убраны пробелы в начале
        assert normalized.endswith("пробелами")  # Убраны пробелы в конце
        
        # Проверяем что нет множественных пробелов/табуляций
        assert "  " not in normalized  # Нет двойных пробелов
        assert "\t" not in normalized  # Нет табуляций
        
        print(f"✓ test_normalize_whitespace_only: '{normalized[:30]}...'")
    
    def test_normalize_empty_text(self):
        """Тест нормализации пустого текста."""
        # Пустая строка
        normalized, stats = self.normalizer.normalize("")
        
        assert normalized == ""
        assert stats.original_length == 0
        assert stats.normalized_length == 0
        
        # None или не строка
        normalized2, stats2 = self.normalizer.normalize(None)
        assert normalized2 == ""
        assert stats2.original_length == 0
        
        print("✓ test_normalize_empty_text: пустой текст обработан корректно")
    
    def test_normalize_aggressive_mode(self):
        """Тест агрессивной нормализации (с пунктуацией)."""
        aggressive_normalizer = TextNormalizer(aggressive_normalization=True)
        
        input_text = "Текст с «кавычками» и — тире… Многоточие.  И   пробелами !"
        
        normalized, _ = aggressive_normalizer.normalize(input_text)
        
        # Проверяем нормализацию кавычек (может заменить на ")
        # Проверяем что убраны лишние пробелы вокруг пунктуации
        assert "  " not in normalized
        assert " !" not in normalized  # Не должно быть пробела перед !
        
        print(f"✓ test_normalize_aggressive_mode: '{normalized[:40]}...'")
    
    def test_normalization_stats(self):
        """Тест сбора статистики нормализации."""
        input_text = "Текст  с   множественными   пробелами\n\n\nи переносами"
        
        normalized, stats = self.normalizer.normalize(input_text)
        
        # Проверяем что статистика заполнена
        assert stats.original_length == len(input_text)
        assert stats.normalized_length == len(normalized)
        assert hasattr(stats, 'spaces_removed')
        assert hasattr(stats, 'linebreaks_normalized')
        assert hasattr(stats, 'special_chars_removed')
        
        # Проверяем преобразование статистики в словарь
        stats_dict = stats.to_dict()
        assert isinstance(stats_dict, dict)
        assert 'original_length' in stats_dict
        assert 'normalized_length' in stats_dict
        
        print(f"✓ test_normalization_stats: статистика собрана: {stats_dict}")


class TestNormalizeTextFunctions:
    """Тесты для функций-оберток."""
    
    def test_normalize_text_function(self):
        """Тест функции normalize_text()."""
        input_text = "  Неотформатированный  текст\t"
        
        normalized = normalize_text(input_text)
        
        # Проверяем базовую нормализацию
        assert normalized.startswith("Неотформатированный")
        assert normalized.endswith("текст")
        assert "  " not in normalized
        assert "\t" not in normalized
        
        print(f"✓ test_normalize_text_function: '{normalized}'")
    
    def test_normalize_text_with_kwargs(self):
        """Тест функции normalize_text() с параметрами."""
        input_text = "Текст [[FORMULA]] с плейсхолдером"
        
        # Без сохранения плейсхолдеров
        normalized1 = normalize_text(input_text, preserve_formula_placeholders=False)
        
        # С сохранением плейсхолдеров
        normalized2 = normalize_text(input_text, preserve_formula_placeholders=True)
        
        # Проверяем что результаты могут отличаться
        assert normalized1 != normalized2 or "[[FORMULA]]" in normalized2
        
        print(f"✓ test_normalize_text_with_kwargs: с параметрами работает")
    
    def test_normalize_whitespace_function(self):
        """Тест функции normalize_whitespace()."""
        input_text = "  Текст  \n\n  с  \t  пробелами  "
        
        normalized = normalize_whitespace(input_text)
        
        # Проверяем нормализацию пробелов
        assert normalized.startswith("Текст")
        assert normalized.endswith("пробелами")
        assert "\t" not in normalized
        assert "  " not in normalized
        
        print(f"✓ test_normalize_whitespace_function: '{normalized}'")
    
    def test_edge_cases(self):
        """Тест граничных случаев для функций."""
        # Пустая строка
        assert normalize_text("") == ""
        assert normalize_whitespace("") == ""
        
        # Только пробелы
        assert normalize_text("   ") == ""
        assert normalize_whitespace("   \t\n  ") == ""
        
        # Очень длинный текст
        long_text = "A" * 1000 + "   " + "B" * 1000
        normalized = normalize_text(long_text)
        assert "   " not in normalized
        assert len(normalized) < len(long_text)
        
        print("✓ test_edge_cases: граничные случаи обработаны")