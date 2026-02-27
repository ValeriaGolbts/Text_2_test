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
            'void', 'main', 'try', 'catch', 'finally', 'throw', 'throws', 'lambda',
            'with', 'as', 'assert', 'del', 'global', 'nonlocal', 'pass', 'break',
            'continue', 'elif', 'except', 'finally', 'raise', 'yield'
        }

        # Символы, часто встречающиеся в коде
        self.code_symbols = {'/', '%', '!', '&', '|', 
                             '^', '~', '?', ':', ';', '{', '}', '[', ']'}
        
        # Паттерн для интерактивного Python (строки, начинающиеся с >>>)
        self.interactive_pattern = re.compile(r'^>>>\s.*$', re.MULTILINE)

    def _looks_like_code_line(self, line: str) -> bool:
        """
        Определяет, похожа ли строка на код на основе эвристик.
        """
        line = line.rstrip('\n')
        if not line:
            return False
        
        # Сначала проверяем, не является ли строка явно текстом
        if self._is_likely_text(line):
            return False
        
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        
        # 1. Интерактивный Python
        if stripped.startswith('>>>'):
            return True
        
        # 2. Ключевые слова как отдельные слова
        words = re.findall(r'\b[a-zA-Z_]\w*\b', stripped)
        if any(kw in words for kw in self.code_keywords):
            # Если ключевое слово найдено, проверяем, что это не часть текста
            # (уже отсекли текст выше)
            return True
        
        # 3. Содержит символы кода с достаточной плотностью
        symbol_count = sum(1 for ch in stripped if ch in self.code_symbols)
        if symbol_count >= 2 and len(stripped) > 5:
            # Проверяем, что символы не только пунктуация типа запятых
            code_specific = any(ch in '=<>{}();' for ch in stripped)
            if code_specific:
                return True
        
        # 4. Заканчивается двоеточием (часто после def, if и т.д.)
        if stripped.endswith(':'):
            return True
        
        # 5. Начинается с отступа и содержит операторы
        if indent > 0:
            # Внутри блока – считаем кодом, если не текст
            return True
        
        return False
    
    def _find_code_blocks_heuristic(self, text: str) -> List[CodeBlock]:
        lines = text.splitlines()
        blocks = []
        i = 0
        while i < len(lines):
            if self._looks_like_code_line(lines[i]):
                start_line = i
                # Идём вперёд, пока строки похожи на код ИЛИ пустые (но внутри блока)
                while i < len(lines):
                    current = lines[i]
                    if self._looks_like_code_line(current) or (current.strip() == '' and i > start_line):
                        i += 1
                    else:
                        # Если это не код и не пустая строка, прерываем блок
                        break
                end_line = i
                block_text = '\n'.join(lines[start_line:end_line])
                # Вычисляем позиции (приблизительно)
                start_pos = text.find(block_text)
                end_pos = start_pos + len(block_text)
                language = self._guess_language(block_text)
                block = CodeBlock(
                    code=block_text,
                    language=language,
                    start_pos=start_pos,
                    end_pos=end_pos
                )
                blocks.append(block)
            else:
                i += 1
        return blocks
    
    def _is_likely_text(self, line: str) -> bool:
        """
        Возвращает True, если строка больше похожа на обычный текст, чем на код.
        """
        stripped = line.strip()
        if not stripped:
            return False
        
        # 1. Начинается с заглавной буквы и заканчивается точкой, вопросительным или восклицательным знаком
        if stripped[0].isupper() and stripped[-1] in '.!?':
            return True
        
        # 2. Содержит много слов (больше 5) и мало специальных символов
        words = stripped.split()
        if len(words) > 5:
            # Считаем долю "кодовых" символов
            symbol_count = sum(1 for ch in stripped if ch in self.code_symbols)
            if symbol_count / len(stripped) < 0.05:  # меньше 5% символов
                return True
        
        # 3. Есть типичные текстовые фразы (предлоги, союзы в большом количестве)
        text_indicators = ['the', 'and', 'or', 'but', 'however', 'therefore', 'это', 'что', 'как', 'для']
        lower = stripped.lower()
        if any(ind in lower.split() for ind in text_indicators):
            # Но не слишком много кодовых символов
            symbol_count = sum(1 for ch in stripped if ch in self.code_symbols)
            if symbol_count < 3:
                return True
        
        return False
    
    def extract(self, text: str) -> List[CodeBlock]:
        blocks = []
        seen = set()  # множество кортежей (start, end) для уникальности
        
        # 1. Явные блоки (markdown)
        for pattern, flags in self.multiline_patterns:
            for match in re.finditer(pattern, text, flags):
                start, end = match.start(), match.end()
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                
                if len(match.groups()) == 2:
                    lang = match.group(1).strip() or self._guess_language(match.group(2))
                    code = match.group(2)
                else:
                    lang = match.group(2).strip() or self._guess_language(match.group(3))
                    code = match.group(3)
                
                block = CodeBlock(code=code, language=lang, start_pos=start, end_pos=end)
                blocks.append(block)
                logger.debug(f"Найден явный блок кода: {block}")
        
        # 2. Эвристические блоки
        heuristic_blocks = self._find_code_blocks_heuristic(text)
        for block in heuristic_blocks:
            # Проверяем, не пересекается ли с уже найденными
            overlap = False
            for (s, e) in seen:
                if not (block.end_pos <= s or block.start_pos >= e):
                    overlap = True
                    break
            if not overlap:
                blocks.append(block)
                seen.add((block.start_pos, block.end_pos))
                logger.debug(f"Найден эвристический блок кода: {block}")
        
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