"""
metrics_calculator.py
Расчет содержательных метрик для оценки качества сгенерированного теста.

На вход:
- output.json: исходные чанки с метаданными
- test_result.json: сгенерированный тест от GigaChat

На выходе:
- Словарь с метриками
- Сохранение результатов в JSON файл

Автор: Для магистерской работы
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
from collections import Counter


class ContentMetricsCalculator:
    """
    Класс для расчета содержательных метрик качества теста.
    
    Метрики:
    1. Покрытие ключевых терминов
    2. Покрытие формул
    3. Self-BLEU (разнообразие вопросов)
    4. Средняя длина вопроса
    5. Доля вопросов с формулами
    6. Распределение типов вопросов
    7. Уникальность терминов
    """
    
    def __init__(self, chunks_path: str, test_path: str):
        """
        Args:
            chunks_path: Путь к output.json (исходные чанки)
            test_path: Путь к test_result.json (сгенерированный тест)
        """
        self.chunks_path = Path(chunks_path)
        self.test_path = Path(test_path)
        
        self.chunks_data = None
        self.test_data = None
        self.all_chunks = []
        self.all_formulas = []
        self.all_terms = []
        self.questions = []
        
    def load_data(self) -> bool:
        """Загружает данные из JSON файлов"""
        try:
            # Загрузка чанков
            with open(self.chunks_path, 'r', encoding='utf-8') as f:
                self.chunks_data = json.load(f)
            self.all_chunks = self.chunks_data.get('chunks', [])
            print(f" Загружены чанки: {len(self.all_chunks)} блоков")
            
            # Загрузка теста
            with open(self.test_path, 'r', encoding='utf-8') as f:
                self.test_data = json.load(f)
            
            # Извлекаем вопросы (поддерживаются разные форматы)
            if 'questions' in self.test_data:
                self.questions = self.test_data['questions']
            elif 'test' in self.test_data and 'questions' in self.test_data['test']:
                self.questions = self.test_data['test']['questions']
            elif 'raw_response' in self.test_data:
                # Пробуем распарсить raw_response
                try:
                    raw = json.loads(self.test_data['raw_response'])
                    self.questions = raw.get('questions', [])
                except:
                    self.questions = []
            else:
                self.questions = []
            
            print(f" Загружен тест: {len(self.questions)} вопросов")
            return True
            
        except FileNotFoundError as e:
            print(f" Файл не найден: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f" Ошибка парсинга JSON: {e}")
            return False
    
    def extract_all_formulas(self) -> Set[str]:
        """
        Извлекает все формулы из чанков.
        Формулы могут быть в полях 'formulas' или внутри текста.
        """
        formulas = set()
        
        for chunk in self.all_chunks:
            # 1. Из поля formulas
            chunk_formulas = chunk.get('formulas', [])
            for f in chunk_formulas:
                original = f.get('original', '')
                normalized = f.get('normalized', '')
                if normalized:
                    formulas.add(self._normalize_formula(normalized))
                elif original:
                    formulas.add(self._normalize_formula(original))
            
            # 2. Из текста (поиск LaTeX формул)
            text = chunk.get('processed_text', '')
            latex_formulas = re.findall(r'\$[^\$]+\$', text)
            for lf in latex_formulas:
                formulas.add(self._normalize_formula(lf))
            
            # 3. Из плейсхолдеров FORMULA_XXX
            placeholders = re.findall(r'\[\[FORMULA_\d+_\d+\]\]', text)
            for ph in placeholders:
                formulas.add(ph)
        
        print(f" Всего уникальных формул в чанках: {len(formulas)}")
        return formulas
    
    def extract_all_terms(self) -> Set[str]:
        """
        Извлекает все ключевые термины из метаданных чанков.
        """
        terms = set()
        
        for chunk in self.all_chunks:
            metadata = chunk.get('metadata', {})
            chunk_terms = metadata.get('key_terms', [])
            terms.update(chunk_terms)
        
        print(f" Всего уникальных терминов в чанках: {len(terms)}")
        return terms
    
    def _normalize_formula(self, formula: str) -> str:
        """Нормализует формулу для сравнения (удаляет пробелы, приводит к нижнему регистру)"""
        if not formula:
            return ""
        # Удаляем лишние пробелы
        normalized = re.sub(r'\s+', ' ', formula.strip())
        # Приводим к нижнему регистру
        normalized = normalized.lower()
        return normalized
    
    def _normalize_term(self, term: str) -> str:
        """Нормализует термин для сравнения"""
        if not term:
            return ""
        return term.lower().strip()
    
    def extract_formulas_from_test(self) -> Set[str]:
        """Извлекает формулы из вопросов теста"""
        formulas = set()
        
        for q in self.questions:
            # Текст вопроса
            question_text = q.get('question', '')
            # Пояснение
            explanation = q.get('explanation', '')
            # Правильный ответ (для закрытых)
            correct_answer = q.get('correct_answer', '')
            # Ожидаемый ответ (для открытых)
            expected_answer = q.get('expected_answer', '')
            
            all_text = f"{question_text} {explanation} {correct_answer} {expected_answer}"
            
            # Поиск LaTeX формул
            latex_formulas = re.findall(r'\$[^\$]+\$', all_text)
            for lf in latex_formulas:
                formulas.add(self._normalize_formula(lf))
            
            # Поиск математических выражений (простые)
            math_expr = re.findall(r'[a-zA-Z]\s*[=<>]\s*[a-zA-Z0-9]+', all_text)
            for me in math_expr:
                formulas.add(self._normalize_formula(me))
        
        print(f" Формул в тесте: {len(formulas)}")
        return formulas
    
    def extract_terms_from_test(self) -> Set[str]:
        """Извлекает ключевые термины из вопросов теста"""
    # Получаем эталонный список терминов из чанков
    all_chunk_terms = self.extract_all_terms()
    
    if not all_chunk_terms:
        print("Нет терминов в чанках")
        return set()
    
    found_terms = set()
    
    for q in self.questions:
        # Собираем весь текст вопроса
        question_text = q.get('question', '').lower()
        explanation = q.get('explanation', '').lower()
        correct_answer = q.get('correct_answer', '').lower()
        expected_answer = q.get('expected_answer', '').lower()
        
        all_text = f"{question_text} {explanation} {correct_answer} {expected_answer}"
        
        # Ищем каждый эталонный термин в тексте вопроса
        for term in all_chunk_terms:
            # Используем нормализацию и поиск с учетом границ слов
            normalized_term = self._normalize_term(term)
            
            # Варианты поиска:
            # 1. Простой поиск подстроки (текущий подход)
            if normalized_term in all_text:
                found_terms.add(term)
                continue
            
            # 2. Поиск с учетом словоформ (более продвинутый)
            # Можно добавить стемминг или лемматизацию
            if self._fuzzy_match_term(normalized_term, all_text):
                found_terms.add(term)
    
    print(f"Терминов из чанков найдено в тесте: {len(found_terms)} из {len(all_chunk_terms)}")
    return found_terms
    
    def calculate_term_coverage(self) -> float:
        """
        Покрытие ключевых терминов.
        Формула: |термины_в_тесте| / |все_термины_в_чанках|
        """
        all_terms = self.extract_all_terms()
        terms_in_test = self.extract_terms_from_test()
        
        if len(all_terms) == 0:
            return 0.0
        
        coverage = len(terms_in_test) / len(all_terms)
        print(f" Покрытие терминов: {coverage:.2%} ({len(terms_in_test)}/{len(all_terms)})")
        return coverage
    
    def calculate_formula_coverage(self) -> float:
        """
        Покрытие формул.
        Формула: |формулы_в_тесте| / |все_формулы_в_чанках|
        """
        all_formulas = self.extract_all_formulas()
        formulas_in_test = self.extract_formulas_from_test()
        
        if len(all_formulas) == 0:
            return 0.0
        
        coverage = len(formulas_in_test) / len(all_formulas)
        print(f" Покрытие формул: {coverage:.2%} ({len(formulas_in_test)}/{len(all_formulas)})")
        return coverage
    
    def calculate_self_bleu(self) -> float:
        """
        Self-BLEU: мера разнообразия вопросов.
        Чем ниже значение, тем разнообразнее вопросы.
        
        Без внешних библиотек используем упрощенную версию на основе n-грамм.
        """
        question_texts = [q.get('question', '') for q in self.questions if q.get('question')]
        
        if len(question_texts) < 2:
            return 0.5  # недостаточно вопросов для оценки
        
        def get_ngrams(text: str, n: int) -> List[str]:
            """Разбивает текст на n-граммы"""
            words = text.lower().split()
            return [' '.join(words[i:i+n]) for i in range(len(words) - n + 1)]
        
        def calculate_ngram_overlap(text1: str, text2: str, n: int) -> float:
            """Вычисляет пересечение n-грамм между двумя текстами"""
            ngrams1 = set(get_ngrams(text1, n))
            ngrams2 = set(get_ngrams(text2, n))
            
            if not ngrams1 or not ngrams2:
                return 0.0
            
            intersection = len(ngrams1 & ngrams2)
            union = len(ngrams1 | ngrams2)
            return intersection / union if union > 0 else 0.0
        
        # Усредняем для 1,2,3-грамм
        bleu_scores = []
        
        for i, q1 in enumerate(question_texts):
            for j, q2 in enumerate(question_texts):
                if i != j:
                    score_1 = calculate_ngram_overlap(q1, q2, 1)
                    score_2 = calculate_ngram_overlap(q1, q2, 2)
                    score_3 = calculate_ngram_overlap(q1, q2, 3)
                    
                    # Взвешенное среднее (больше вес для более длинных n-грамм)
                    combined = (score_1 * 0.2 + score_2 * 0.3 + score_3 * 0.5)
                    bleu_scores.append(combined)
        
        if not bleu_scores:
            return 0.5
        
        self_bleu = sum(bleu_scores) / len(bleu_scores)
        print(f" Self-BLEU: {self_bleu:.3f} (чем ниже, тем разнообразнее)")
        return self_bleu
    
    def calculate_avg_question_length(self) -> float:
        """Средняя длина вопроса в символах"""
        if not self.questions:
            return 0.0
        
        lengths = [len(q.get('question', '')) for q in self.questions]
        avg_length = sum(lengths) / len(lengths)
        print(f" Средняя длина вопроса: {avg_length:.0f} символов")
        return avg_length
    
    def calculate_formula_density_in_test(self) -> float:
        """Доля вопросов, содержащих формулы"""
        if not self.questions:
            return 0.0
        
        formula_pattern = re.compile(r'\$[^\$]+\$|\\[a-zA-Z]+')
        
        questions_with_formulas = 0
        for q in self.questions:
            question_text = q.get('question', '')
            if formula_pattern.search(question_text):
                questions_with_formulas += 1
        
        density = questions_with_formulas / len(self.questions)
        print(f" Доля вопросов с формулами: {density:.2%}")
        return density
    
    def calculate_question_types_distribution(self) -> Dict[str, int]:
        """Распределение типов вопросов (open/closed)"""
        if not self.questions:
            return {"open": 0, "closed": 0, "other": 0}
        
        types_count = Counter()
        for q in self.questions:
            q_type = q.get('type', 'unknown').lower()
            types_count[q_type] += 1
        
        print(f"📊 Типы вопросов: {dict(types_count)}")
        return dict(types_count)
    
    def calculate_term_uniqueness(self) -> float:
        """
        Уникальность терминов: отношение уникальных терминов к общему количеству
        вхождений терминов в вопросы.
        """
        if not self.questions:
            return 0.0
        
        # Собираем все термины из вопросов
        all_terms_found = []
        math_terms = [
            'функция', 'производная', 'интеграл', 'предел', 'ряд', 'матрица',
            'вектор', 'уравнение', 'множество', 'число', 'комплексный',
            'модуль', 'аргумент', 'корень', 'степень', 'логарифм', 'синус',
            'косинус', 'тангенс', 'первообразная', 'дифференцирование'
        ]
        
        for q in self.questions:
            question_text = q.get('question', '').lower()
            for term in math_terms:
                if term in question_text:
                    all_terms_found.append(term)
        
        if not all_terms_found:
            return 0.0
        
        unique_terms = len(set(all_terms_found))
        total_terms = len(all_terms_found)
        uniqueness = unique_terms / total_terms
        
        print(f" Уникальность терминов: {uniqueness:.2%}")
        return uniqueness
    
    def calculate_all_metrics(self) -> Dict[str, Any]:
        """
        Рассчитывает все метрики и возвращает словарь с результатами.
        """
        
        print("РАСЧЕТ СОДЕРЖАТЕЛЬНЫХ МЕТРИК")
        
        if not self.load_data():
            return {"error": "Не удалось загрузить данные"}
        
        metrics = {
            # Метаинформация
            "source_chunks_file": str(self.chunks_path),
            "source_test_file": str(self.test_path),
            "total_chunks": len(self.all_chunks),
            "total_questions": len(self.questions),
            
            # Основные метрики
            "term_coverage": self.calculate_term_coverage(),
            "formula_coverage": self.calculate_formula_coverage(),
            "self_bleu": self.calculate_self_bleu(),
            "avg_question_length": self.calculate_avg_question_length(),
            "formula_density_in_test": self.calculate_formula_density_in_test(),
            "question_types": self.calculate_question_types_distribution(),
            "term_uniqueness": self.calculate_term_uniqueness(),
        }
        
        # Дополнительные вычисления
        metrics["diversity_score"] = 1 - metrics["self_bleu"]  # чем выше, тем разнообразнее
        metrics["quality_score"] = (
            metrics["term_coverage"] * 0.3 +
            metrics["formula_coverage"] * 0.3 +
            metrics["diversity_score"] * 0.2 +
            metrics["formula_density_in_test"] * 0.2
        )
        
      
        print("ИТОГОВЫЕ МЕТРИКИ")
        print(f" Quality Score: {metrics['quality_score']:.3f}")
        print(f"    Покрытие терминов: {metrics['term_coverage']:.2%}")
        print(f"    Покрытие формул: {metrics['formula_coverage']:.2%}")
        print(f"    Diversity Score: {metrics['diversity_score']:.3f}")
        print(f"    Формулы в вопросах: {metrics['formula_density_in_test']:.2%}")
        
        return metrics
    
    def save_metrics(self, metrics: Dict[str, Any], output_path: str = None) -> str:
        """Сохраняет метрики в JSON файл"""
        if output_path is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"metrics_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        
        print(f"\n Метрики сохранены в: {output_path}")
        return output_path
    
    def print_comparison_table(self):
        """Выводит таблицу для сравнения с другими стратегиями"""
        print("ТАБЛИЦА ДЛЯ СРАВНЕНИЯ СТРАТЕГИЙ")
        print(f"{'Метрика':<30} | {'Значение':<15}")
        print("-" * 50)
        print(f"{'Покрытие терминов':<30} | {self.calculate_term_coverage():.2%}")
        print(f"{'Покрытие формул':<30} | {self.calculate_formula_coverage():.2%}")
        print(f"{'Self-BLEU':<30} | {self.calculate_self_bleu():.3f}")
        print(f"{'Diversity Score (1 - Self-BLEU)':<30} | {1 - self.calculate_self_bleu():.3f}")
        print(f"{'Средняя длина вопроса':<30} | {self.calculate_avg_question_length():.0f}")
        print(f"{'Доля вопросов с формулами':<30} | {self.calculate_formula_density_in_test():.2%}")
        print(f"{'Уникальность терминов':<30} | {self.calculate_term_uniqueness():.2%}")



def main():
    """Основная функция для запуска из командной строки"""
    import sys
    
    # Параметры по умолчанию
    chunks_file = "output.json"
    test_file = "test_original.json"
    
    # Чтение аргументов командной строки
    if len(sys.argv) > 1:
        chunks_file = sys.argv[1]
    if len(sys.argv) > 2:
        test_file = sys.argv[2]
    
    print(f" Файл с чанками: {chunks_file}")
    print(f" Файл с тестом: {test_file}")
    
    # Расчет метрик
    calculator = ContentMetricsCalculator(chunks_file, test_file)
    metrics = calculator.calculate_all_metrics()
    
    # Сохранение
    calculator.save_metrics(metrics)
    calculator.print_comparison_table()
    
    return metrics


if __name__ == "__main__":
    main()
