"""
Модуль для обнаружения блоков программного кода в тексте.
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CodeBlock:
    """Представляет блок кода, найденный в тексте."""
    
    def __init__(self, code: str, language: str, start_pos: int, end_pos: int):
        self.code = code
        self.language = language
        self.start_pos = start_pos
        self.end_pos = end_pos
    
    def __repr__(self):
        return f"CodeBlock(lang={self.language}, pos={self.start_pos}-{self.end_pos})"


class CodeExtractor:
    """Извлекает блоки программного кода из текста."""
    
    def __init__(self):
        # Паттерны для многострочных блоков кода (markdown, reStructuredText и т.п.)
        self.multiline_patterns = [
            (r'```(\w*)\n(.*?)\n```', re.DOTALL),           # ```python ... ```
            (r'~~~(\w*)\n(.*?)\n~~~', re.DOTALL),           # ~~~python ... ~~~
            (r'^(\s*)```(\w*)\n(.*?)\n\1```', re.MULTILINE | re.DOTALL),  # с отступами
        ]
        
        # Ключевые слова, характерные для кода (для эвристики)
        self.code_keywords = {
            'def', 'class', 'import', 'from', 'if', 'else', 'elif', 'for', 'while',
            'return', 'function', 'var', 'let', 'const', 'int', 'float', 'string',
            'bool', 'true', 'false', 'null', 'undefined', 'print', 'console.log',
            'include', 'define', 'public', 'private', 'protected', 'static',
            'void', 'main', 'try', 'catch', 'finally', 'throw', 'throws'
        }
    
    def extract(self, text: str) -> List[CodeBlock]:
        blocks = []
        seen = set()  # множество кортежей (start, end) для уникальности
        
        for pattern, flags in self.multiline_patterns:
            for match in re.finditer(pattern, text, flags):
                start, end = match.start(), match.end()
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                
                # определение языка и кода 
                if len(match.groups()) == 2:
                    lang = match.group(1).strip() or self._guess_language(match.group(2))
                    code = match.group(2)
                else:
                    lang = match.group(2).strip() or self._guess_language(match.group(3))
                    code = match.group(3)
                
                block = CodeBlock(code=code, language=lang, start_pos=start, end_pos=end)
                blocks.append(block)
                logger.debug(f"Найден блок кода: {block}")
        
        blocks.sort(key=lambda b: b.start_pos)
        return blocks
    
    def _guess_language(self, code_snippet: str) -> str:
        """
        Пытается угадать язык программирования по содержимому.
        Возвращает строку с названием языка или "unknown".
        """
        # Простая эвристика
        code_sample = code_snippet[:500].lower()
        
        if 'def ' in code_sample and ':' in code_sample:
            return 'python'
        if 'function ' in code_sample and '{' in code_sample:
            return 'javascript'
        if 'public static void main' in code_sample:
            return 'java'
        if '#include' in code_sample and ('<' in code_sample or '"' in code_sample):
            return 'c/c++'
        if 'using namespace std;' in code_sample:
            return 'c++'
        if 'package ' in code_sample and ';' in code_sample:
            return 'java'
        
        return 'unknown'
    
    def replace_with_placeholders(self, text: str, blocks: List[CodeBlock]) -> str:
        """
        Заменяет найденные блоки кода на плейсхолдеры.
        Возвращает текст с плейсхолдерами.
        """
        # Работаем от конца к началу, чтобы не сбивать позиции
        result = text
        for block in reversed(blocks):
            placeholder = f"[[CODE_{block.start_pos}_{block.language}]]"
            result = result[:block.start_pos] + placeholder + result[block.end_pos:]
        return result
    
    def restore_from_placeholders(self, text_with_placeholders: str, blocks: List[CodeBlock]) -> str:
        """
        Восстанавливает код из плейсхолдеров.
        """
        result = text_with_placeholders
        for block in blocks:
            placeholder = f"[[CODE_{block.start_pos}_{block.language}]]"
            result = result.replace(placeholder, block.code)
        return result