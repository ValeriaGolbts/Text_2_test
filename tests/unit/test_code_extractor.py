"""
Тесты для модуля извлечения кода.
"""

import pytest
from src.code_extractor import CodeExtractor, CodeBlock


class TestCodeExtractor:
    
    def setup_method(self):
        self.extractor = CodeExtractor()
    
    def test_extract_simple_python_block(self):
        text = "Вот код:\n```python\nprint('Hello')\n```\nКонец."
        blocks = self.extractor.extract(text)
        assert len(blocks) == 1
        block = blocks[0]
        assert block.language == 'python'
        assert block.code == "print('Hello')"
        # Проверяем позиции (необязательно, но можно)
        assert text[block.start_pos:block.end_pos] == "```python\nprint('Hello')\n```"
    
    def test_extract_no_language(self):
        text = "```\nx = 5\n```"
        blocks = self.extractor.extract(text)
        assert len(blocks) == 1
        # язык должен определиться как unknown или по эвристике
        assert blocks[0].language in ('unknown', 'python')
    
    def test_multiple_blocks(self):
        text = "a\n```c\nint a;\n```\nb\n```java\nclass A {}\n```\nc"
        blocks = self.extractor.extract(text)
        assert len(blocks) == 2
        assert blocks[0].language in ('c', 'c/c++')
        assert blocks[1].language in ('java', 'unknown')
    
    def test_replace_placeholders(self):
        text = "start\n```\ncode\n```\nend"
        blocks = self.extractor.extract(text)
        new_text = self.extractor.replace_with_placeholders(text, blocks)
        assert "[[CODE_" in new_text
        assert "code" not in new_text
        # Проверяем, что исходный текст сократился
        #assert len(new_text) < len(text)
    
    def test_restore_from_placeholders(self):
        text = "start\n```\ncode\n```\nend"
        blocks = self.extractor.extract(text)
        new_text = self.extractor.replace_with_placeholders(text, blocks)
        restored = self.extractor.restore_from_placeholders(new_text, blocks)
        
        # Проверяем, что восстановленный текст содержит код
        assert "code" in restored
        # Проверяем, что нет плейсхолдеров
        assert "[[CODE_" not in restored
        # Проверяем, что обрамление (```) не восстановлено – это нормально
        assert "```" not in restored
        # Проверяем, что текст до и после сохранился
        assert restored.startswith("start\n")
        assert restored.endswith("\nend")
        # Можем также проверить, что между start и end только код
        assert restored == "start\ncode\nend"
    
    def test_guess_language_python(self):
        code = "def hello():\n    print('hi')"
        assert self.extractor._guess_language(code) == 'python'
    
    def test_guess_language_java(self):
        code = "public static void main(String[] args) {}"
        assert self.extractor._guess_language(code) == 'java'