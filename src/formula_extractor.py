"""
Модуль для обнаружения и нормализации математических формул в тексте.

Поддерживает формулы в формате LaTeX (inline: $...$, display: \[...\])
и plain-text формулы (например, E = mc^2).
"""

import re
import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from src.data_models import Formula, FormulaType

logger = logging.getLogger(__name__)


class DetectionMethod(str, Enum):
    """Методы обнаружения формул."""
    LATEX_INLINE = "latex_inline"      # $...$
    LATEX_DISPLAY = "latex_display"    # \[...\]
    PLAIN_TEXT = "plain_text"          # Текстовые формулы
    ALL = "all"                        # Все методы


@dataclass
class FormulaDetectionResult:
    """Результат обнаружения формул."""
    
    formulas: List[Formula]
    """Найденные формулы."""
    
    text_with_placeholders: str
    """Текст с замененными формулами на плейсхолдеры."""
    
    placeholder_to_formula: Dict[str, Formula]
    """Соответствие плейсхолдеров формулам."""
    
    detection_stats: Dict[str, int] = field(default_factory=dict)
    """Статистика обнаружения по типам."""


class FormulaExtractor:
    """Класс для обнаружения и обработки математических формул."""
    
    def __init__(self, 
                 detect_plain_text: bool = True,
                 min_plain_text_length: int = 5,
                 max_plain_text_length: int = 100):
        """
        Инициализирует экстрактор формул.
        
        Args:
            detect_plain_text: Обнаруживать ли plain-text формулы
            min_plain_text_length: Минимальная длина plain-text формулы
            max_plain_text_length: Максимальная длина plain-text формулы
        """
        self.detect_plain_text = detect_plain_text
        self.min_plain_text_length = min_plain_text_length
        self.max_plain_text_length = max_plain_text_length
        
        # Компилируем регулярные выражения
        self._compile_patterns()
        
        # Для отслеживания плейсхолдеров
        self._placeholder_counter = 0
        
        logger.info(f"Инициализирован FormulaExtractor (plain-text: {detect_plain_text})")
    
    def _compile_patterns(self):
        """Компилирует регулярные выражения для поиска формул."""
        
        # LaTeX inline формулы: $...$ (но не \$ как символ доллара)
        # Используем negative lookbehind чтобы не находить escaped доллары
        self.latex_inline_pattern = re.compile(
            r'(?<!\\)\$(?!\$)(.*?)(?<!\\)\$(?!\$)',
            re.DOTALL
        )
        
        # LaTeX display формулы: \[...\] или $$...$$
        self.latex_display_pattern = re.compile(
            r'(\\\[.*?\\\])|(\$\$.*?\$\$)',
            re.DOTALL
        )
        
        # Паттерн для plain-text формул
        self.plain_text_pattern = re.compile(
            r'(?:(?<=\s)|^)'                          # начало слова или пробел
            r'[A-Za-zα-ωΑ-Ω0-9_]+'                    # обязательная буква/цифра
            r'(?:\s*[=+\-*/^<>≤≥≠≈∼∝∫∑∏√∛∜∂∇∆]\s*'    # оператор
            r'[A-Za-zα-ωΑ-Ω0-9_+\-*/^().,\[\]{}]*)*'  # остаток выражения
            r'(?=\s|$|[.,;!?])'                        # заканчивается пробелом или пунктуацией
        )
        
        # Паттерн для определения, является ли текст формулой
        self.is_formula_pattern = re.compile(
            r'.*[=+\-*/^<>≤≥≠≈∼∝∫∑∏√∛∜∂∇∆].*|'
            r'.*\\[a-zA-Z]+.*'
        )
        
        # Паттерн для поиска математических операторов
        self.math_operators = set('=+-*/^<>()[]{}|\\')
        
        logger.debug("Паттерны для формул скомпилированы")
    
    def extract(self, text: str, methods: DetectionMethod = DetectionMethod.ALL) -> FormulaDetectionResult:
        """
        Основной метод для извлечения формул из текста.
        
        Args:
            text: Текст для анализа
            methods: Методы обнаружения
            
        Returns:
            FormulaDetectionResult с найденными формулами
        """
        if not text:
            logger.warning("Получен пустой текст для извлечения формул")
            return FormulaDetectionResult([], text, {})
        
        all_formulas = []
        current_text = text
        detection_stats = {
            "latex_inline": 0,
            "latex_display": 0,
            "plain_text": 0,
            "total": 0
        }
        
        # Сброс счетчика плейсхолдеров
        self._placeholder_counter = 0
        
        # Шаг 1: Ищем LaTeX display формулы (\[...\] или $$...$$)
        if methods in [DetectionMethod.LATEX_DISPLAY, DetectionMethod.ALL]:
            formulas, current_text = self._extract_latex_display(current_text, text)
            all_formulas.extend(formulas)
            detection_stats["latex_display"] = len(formulas)
        
        # Шаг 2: Ищем LaTeX inline формулы ($...$)
        if methods in [DetectionMethod.LATEX_INLINE, DetectionMethod.ALL]:
            formulas, current_text = self._extract_latex_inline(current_text, text)
            all_formulas.extend(formulas)
            detection_stats["latex_inline"] = len(formulas)
        
        # Шаг 3: Ищем plain-text формулы (если включено)
        if self.detect_plain_text and methods in [DetectionMethod.PLAIN_TEXT, DetectionMethod.ALL]:
            formulas, current_text = self._extract_plain_text(current_text, text)
            all_formulas.extend(formulas)
            detection_stats["plain_text"] = len(formulas)
        
        # Сортируем формулы по позиции
        all_formulas.sort(key=lambda f: f.start_pos)
        
        # Обновляем общую статистику
        detection_stats["total"] = len(all_formulas)
        
        # Создаем маппинг плейсхолдеров
        placeholder_to_formula = {}
        for formula in all_formulas:
            placeholder = f"[[FORMULA_{formula.start_pos}]]"
            placeholder_to_formula[placeholder] = formula
        
        logger.info(f"Найдено формул: {detection_stats['total']} "
                   f"(LaTeX inline: {detection_stats['latex_inline']}, "
                   f"display: {detection_stats['latex_display']}, "
                   f"plain: {detection_stats['plain_text']})")
        
        return FormulaDetectionResult(
            formulas=all_formulas,
            text_with_placeholders=current_text,
            placeholder_to_formula=placeholder_to_formula,
            detection_stats=detection_stats
        )
    
    def _extract_latex_inline(self, text: str, original_text: str) -> Tuple[List[Formula], str]:
        """
        Извлекает LaTeX inline формулы ($...$).
        
        Args:
            text: Текст для анализа (уже с замененными display формулами)
            original_text: Оригинальный текст (для позиций)
            
        Returns:
            Кортеж (список формул, текст с плейсхолдерами)
        """
        formulas = []
        
        # Ищем все вхождения
        for match in self.latex_inline_pattern.finditer(text):
            formula_text = match.group(1)

            # Игнорируем, если внутри только цифры или слишком коротко
            if len(formula_text.strip()) < self.min_plain_text_length:
                continue
            if not re.search(r'[a-zA-Zα-ωΑ-Ω=+\-*/^()]', formula_text):
                continue

            start_pos = match.start()
            end_pos = match.end()

            # Пропускаем, если внутри только цифры или коротко
            if not re.search(r'[a-zA-Zα-ωΑ-Ω=+\-*/^]', formula_text):
                continue
            
            # Проверяем, что формула не слишком короткая (не просто "$a$")
            if len(formula_text.strip()) >= self.min_plain_text_length:
                # Нормализуем формулу
                normalized = self._normalize_formula(formula_text, FormulaType.LATEX_INLINE)
                
                formula = Formula(
                    original=formula_text,
                    normalized=normalized,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    formula_type=FormulaType.LATEX_INLINE
                )
                
                formulas.append(formula)
                
                # Создаем плейсхолдер
                placeholder = self._create_placeholder(start_pos)
                
                # Заменяем формулу на плейсхолдер в тексте
                text = text[:match.start()] + placeholder + text[match.end():]
        
        return formulas, text
    
    def _extract_latex_display(self, text: str, original_text: str) -> Tuple[List[Formula], str]:
        """
        Извлекает LaTeX display формулы (\[...\] или $$...$$).
        
        Args:
            text: Текст для анализа
            original_text: Оригинальный текст (для позиций)
            
        Returns:
            Кортеж (список формул, текст с плейсхолдерами)
        """
        formulas = []
        
        # Ищем все вхождения
        for match in self.latex_display_pattern.finditer(text):
            formula_text = match.group(0)
            start_pos = match.start()
            end_pos = match.end()
            
            # Убираем обрамляющие символы
            if formula_text.startswith('\\['):
                clean_text = formula_text[2:-2]  # Убираем \[ и \]
            else:  # $$...$$
                clean_text = formula_text[2:-2]  # Убираем $$ и $$
            
            # Нормализуем формулу
            normalized = self._normalize_formula(clean_text, FormulaType.LATEX_DISPLAY)
            
            formula = Formula(
                original=formula_text,
                normalized=normalized,
                start_pos=start_pos,
                end_pos=end_pos,
                formula_type=FormulaType.LATEX_DISPLAY
            )
            
            formulas.append(formula)
            
            # Создаем плейсхолдер
            placeholder = self._create_placeholder(start_pos)
            
            # Заменяем формулу на плейсхолдер в тексте
            text = text[:match.start()] + placeholder + text[match.end():]
        
        return formulas, text
    
    def _extract_plain_text(self, text: str, original_text: str) -> Tuple[List[Formula], str]:
        """
        Извлекает plain-text формулы.
        """
        formulas = []
        # Сначала собираем все совпадения из оригинального текста
        for match in self.plain_text_pattern.finditer(text):
            formula_text = match.group(0)
            start_pos = match.start()
            end_pos = match.end()
            
            # Пропускаем, если содержит плейсхолдеры
            if '[[FORMULA_' in formula_text:
                continue
            
            if len(formula_text) < self.min_plain_text_length:
                continue
            if len(formula_text) > self.max_plain_text_length:
                continue
            
            if not self._looks_like_formula(formula_text):
                continue
            
            normalized = self._normalize_plain_text_formula(formula_text)
            # Пропускаем одиночные числа и короткие цифровые последовательности
            if re.fullmatch(r'[\d\s\.\+\-\*/]*', formula_text) and len(formula_text) < 5:
                continue
            formula = Formula(
                original=formula_text,
                normalized=normalized,
                start_pos=start_pos,
                end_pos=end_pos,
                formula_type=FormulaType.PLAIN_TEXT
            )
            formulas.append(formula)
        
        # Заменяем найденные формулы на плейсхолдеры, идя с конца
        text_with_placeholders = text
        for formula in sorted(formulas, key=lambda f: f.start_pos, reverse=True):
            placeholder = self._create_placeholder(formula.start_pos)
            text_with_placeholders = (
                text_with_placeholders[:formula.start_pos] 
                + placeholder 
                + text_with_placeholders[formula.end_pos:]
            )
        
        return formulas, text_with_placeholders
    
    def _find_formula_start(self, text: str, pos: int) -> int:
        """Находит начало формулы."""
        start = pos
        # Идем назад пока находим символы формулы
        while start > 0 and (text[start-1].isalnum() or text[start-1] in ' _+-*/^<>()[]{}'):
            start -= 1
        return start
    
    def _find_formula_end(self, text: str, pos: int) -> int:
        """Находит конец формулы."""
        end = pos + 1
        # Идем вперед пока находим символы формулы
        while end < len(text) and (text[end].isalnum() or text[end] in ' _+-*/^<>()[]{}.,;:'):
            end += 1
        return end
    
    def _looks_like_formula(self, text: str) -> bool:
        """Проверяет, похож ли текст на формулу."""

        # Если строка состоит только из цифр, точки и пробелов, и она короткая – не формула
        if re.fullmatch(r'[\d\s\.]+', text.strip()) and len(text.strip()) <= 4:
            return False
        # Должен содержать хотя бы один математический оператор
        if not any(op in text for op in self.math_operators):
            return False
        
        # Не должен состоять преимущественно из букв (более 80%)
        letters = sum(c.isalpha() for c in text)
        total = len(text)
        if total == 0:
            return False
        if letters / total > 0.8:
            # Если много букв, но есть греческие символы – возможно, формула
            if not re.search(r'[α-ωΑ-Ω]', text):
                return False
        
        # Должна содержать хотя бы одну цифру или быть короткой
        if not re.search(r'\d', text) and len(text) > 10:
            # Длинные тексты без цифр вряд ли формулы
            return False
        
        return True
    
    def _normalize_formula(self, formula_text: str, formula_type: FormulaType) -> str:
        """
        Нормализует формулу (приводит к единому виду).
        
        Args:
            formula_text: Текст формулы
            formula_type: Тип формулы
            
        Returns:
            Нормализованная формула
        """
        if formula_type == FormulaType.PLAIN_TEXT:
            return self._normalize_plain_text_formula(formula_text)
        else:  # LaTeX формулы
            return self._normalize_latex_formula(formula_text)
    
    def _normalize_latex_formula(self, formula_text: str) -> str:
        """Нормализует LaTeX формулу."""
        # Убираем лишние пробелы
        formula_text = re.sub(r'\s+', ' ', formula_text.strip())
        
        # Заменяем синонимы операторов
        replacements = {
            r'\\cdot': '*',
            r'\\times': '*',
            r'\^': '**',  # Для Python-стиля
            r'\\frac\{([^}]+)\}\{([^}]+)\}': r'(\1)/(\2)',
            r'\\sqrt\{([^}]+)\}': r'sqrt(\1)',
            r'\\sum_': 'sum_',
            r'\\int_': 'int_',
        }
        
        for pattern, replacement in replacements.items():
            formula_text = re.sub(pattern, replacement, formula_text)
        
        return formula_text
    
    def _normalize_plain_text_formula(self, formula_text: str) -> str:
        """Нормализует plain-text формулу."""
        # Убираем лишние пробелы
        formula_text = re.sub(r'\s+', ' ', formula_text.strip())
        
        # Стандартизируем операторы
        replacements = {
            '×': '*',
            '·': '*',
            '÷': '/',
            '^': '**',  # Для Python-стиля
            '–': '-',   # Длинное тире на минус
            '—': '-',
        }
        
        for old, new in replacements.items():
            formula_text = formula_text.replace(old, new)
        
        return formula_text
    
    def _create_placeholder(self, position: int) -> str:
        """Создает уникальный плейсхолдер для формулы."""
        self._placeholder_counter += 1
        return f"[[FORMULA_{position}_{self._placeholder_counter}]]"
    
    def restore_formulas(self, text_with_placeholders: str, placeholder_to_formula: Dict[str, Formula]) -> str:
        """
        Восстанавливает формулы в тексте.
        
        Args:
            text_with_placeholders: Текст с плейсхолдерами
            placeholder_to_formula: Соответствие плейсхолдеров формулам
            
        Returns:
            Текст с восстановленными формулами
        """
        result = text_with_placeholders
        
        for placeholder, formula in placeholder_to_formula.items():
            result = result.replace(placeholder, formula.original)
        
        return result
    
def extract_formulas(text: str, **kwargs) -> FormulaDetectionResult:
    """
    Функция для быстрого извлечения формул.
    
    Args:
        text: Текст для анализа
        **kwargs: Аргументы для FormulaExtractor
        
    Returns:
        FormulaDetectionResult
    """
    extractor = FormulaExtractor(**kwargs)
    return extractor.extract(text)


def replace_formulas_with_placeholders(text: str) -> Tuple[str, List[Formula]]:
    """
    Быстрая замена формул на плейсхолдеры.
    
    Args:
        text: Текст для обработки
        
    Returns:
        Кортеж (текст с плейсхолдерами, список формул)
    """
    extractor = FormulaExtractor()
    result = extractor.extract(text)
    return result.text_with_placeholders, result.formulas


