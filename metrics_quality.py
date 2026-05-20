"""
metrics_quality.py
Специализированные метрики для оценки качества теста по технической дисциплине.

Проверяет:
- Соблюдение уровня сложности
- Качество дистракторов (правдоподобность)
- Однозначность ответа
- Формат вопросов

Результаты сохраняются в JSON файл.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import Counter
from datetime import datetime


class TestQualityMetrics:
    """
    Метрики качества теста для технической дисциплины в вузе.
    """
    
    def __init__(self, test_result: Dict, test_path: str = None):
        """
        Args:
            test_result: Результат генерации теста (JSON)
            test_path: Путь к исходному файлу теста (для метаданных)
        """
        self.test = test_result
        self.test_path = test_path
        self.questions = test_result.get('questions', [])
        
    def check_question_count(self, expected: int = 10) -> Dict:
        """Проверяет количество вопросов"""
        actual = len(self.questions)
        return {
            "metric": "Количество вопросов",
            "expected": expected,
            "actual": actual,
            "is_valid": actual == expected,
            "score": 1.0 if actual == expected else 1.0 - abs(actual - expected) / expected
        }
    
    def check_question_type(self, expected_type: str = "closed") -> Dict:
        """Проверяет тип вопросов (должны быть закрытыми)"""
        if not self.questions:
            return {"metric": "Тип вопросов", "is_valid": False, "score": 0}
        
        closed_count = sum(1 for q in self.questions if q.get('type') == 'closed')
        ratio = closed_count / len(self.questions)
        
        return {
            "metric": "Тип вопросов",
            "expected": expected_type,
            "closed_ratio": ratio,
            "is_valid": ratio == 1.0,
            "score": ratio
        }
    
    def check_options_count(self, expected: int = 4) -> Dict:
        """Проверяет количество вариантов ответа (должно быть 4)"""
        if not self.questions:
            return {"metric": "Количество вариантов", "is_valid": False, "score": 0}
        
        correct_count = 0
        for q in self.questions:
            options = q.get('options', [])
            if len(options) == expected:
                correct_count += 1
        
        ratio = correct_count / len(self.questions)
        
        return {
            "metric": "Количество вариантов",
            "expected": expected,
            "correct_count": correct_count,
            "total": len(self.questions),
            "ratio": ratio,
            "is_valid": ratio == 1.0,
            "score": ratio
        }
    
    def check_answer_uniqueness(self) -> Dict:
        """Проверяет однозначность ответа (только один правильный вариант)"""
        if not self.questions:
            return {"metric": "Однозначность ответа", "is_valid": False, "score": 0}
        
        issues = []
        for q in self.questions:
            options = q.get('options', [])
            correct = q.get('correct_answer', '')
            
            # Проверяем, что правильный ответ есть среди вариантов
            if correct not in options:
                issues.append({
                    "question_id": q.get('id'),
                    "issue": "Правильный ответ отсутствует среди вариантов"
                })
            
            # Проверяем, что только один вариант считается правильным
            correct_in_options = sum(1 for opt in options if opt == correct)
            if correct_in_options > 1:
                issues.append({
                    "question_id": q.get('id'),
                    "issue": "Несколько вариантов отмечены как правильные"
                })
        
        is_valid = len(issues) == 0
        score = 1.0 if is_valid else 0.5
        
        return {
            "metric": "Однозначность ответа",
            "is_valid": is_valid,
            "issues": issues,
            "score": score
        }
    
    def check_distractor_quality(self) -> Dict:
        """
        Проверяет качество дистракторов (правдоподобность).
        
        Критерии:
        - Дистракторы не должны быть слишком короткими/очевидными
        - Не должны повторять правильный ответ
        - Должны быть разнообразными
        - Должен быть семантически схожим с вопросом 
        - Должно соблюдаться семантическое различие дистрактора с ответом
        """
        if not self.questions:
            return {"metric": "Качество дистракторов", "is_valid": False, "score": 0}
        
        distractor_issues = []
        total_distractors = 0
        quality_score = 0
        
        for q in self.questions:
            options = q.get('options', [])
            correct = q.get('correct_answer', '')
            distractors = [opt for opt in options if opt != correct]
            total_distractors += len(distractors)
            
            # Критерий 1: Дистракторы не должны быть пустыми
            empty_distractors = [d for d in distractors if len(d.strip()) < 5]
            if empty_distractors:
                distractor_issues.append({
                    "question_id": q.get('id'),
                    "issue": "Слишком короткие дистракторы",
                    "distractors": empty_distractors
                })
            
            # Критерий 2: Дистракторы не должны дублироваться
            unique_distractors = set(distractors)
            if len(unique_distractors) != len(distractors):
                distractor_issues.append({
                    "question_id": q.get('id'),
                    "issue": "Повторяющиеся дистракторы"
                })
            
            # Критерий 3: Дистракторы должны быть правдоподобными (проверка длины)
            # Хороший дистрактор: 20-150 символов
            good_distractors = [d for d in distractors if 20 <= len(d) <= 150]
            quality_score += len(good_distractors) / max(len(distractors), 1)
        
        avg_quality = quality_score / max(len(self.questions), 1)
        
        return {
            "metric": "Качество дистракторов",
            "total_distractors": total_distractors,
            "issues_count": len(distractor_issues),
            "avg_quality_score": avg_quality,
            "issues": distractor_issues,
            "score": avg_quality
        }
    
    def check_formula_usage(self) -> Dict:
        """Проверяет использование формул в вопросах"""
        if not self.questions:
            return {"metric": "Использование формул", "is_valid": False, "score": 0}
        
        formula_pattern = re.compile(r'\$[^\$]+\$|\\[a-zA-Z]+')
        
        questions_with_formulas = 0
        for q in self.questions:
            question_text = q.get('question', '')
            if formula_pattern.search(question_text):
                questions_with_formulas += 1
        
        ratio = questions_with_formulas / len(self.questions)
        
        return {
            "metric": "Использование формул",
            "questions_with_formulas": questions_with_formulas,
            "total_questions": len(self.questions),
            "ratio": ratio,
            "is_valid": ratio >= 0.5,  # минимум 50% вопросов с формулами
            "score": min(1.0, ratio / 0.7)  # идеал 70%
        }
    
    def check_difficulty_level(self) -> Dict:
        """
        Проверяет уровень сложности (средний).
        
        Признаки среднего уровня:
        - Вопросы требуют применения формул
        - Есть вопросы на анализ, а не только на запоминание
        - Вопросы не слишком тривиальные
        """
        if not self.questions:
            return {"metric": "Уровень сложности", "is_valid": False, "score": 0}
        
        # Ключевые слова для определения сложности
        easy_keywords = ['определение', 'что такое', 'какой', 'верно ли']
        medium_keywords = ['вычислите', 'найдите', 'определите', 'докажите', 'примените']
        hard_keywords = ['проанализируйте', 'синтезируйте', 'оцените', 'сравните']
        
        medium_count = 0
        for q in self.questions:
            question_lower = q.get('question', '').lower()
            
            if any(kw in question_lower for kw in medium_keywords):
                medium_count += 1
            elif any(kw in question_lower for kw in hard_keywords):
                medium_count += 0.8  # сложные вопросы тоже подходят
            elif any(kw in question_lower for kw in easy_keywords):
                medium_count += 0.3  # легкие вопросы снижают среднюю сложность
        
        score = medium_count / max(len(self.questions), 1)
        
        return {
            "metric": "Уровень сложности",
            "expected": "medium",
            "medium_ratio": score,
            "is_valid": score >= 0.5,
            "score": score
        }
    
    def check_explanation_quality(self) -> Dict:
        """Проверяет качество пояснений к вопросам"""
        if not self.questions:
            return {"metric": "Качество пояснений", "is_valid": False, "score": 0}
        
        good_explanations = 0
        for q in self.questions:
            explanation = q.get('explanation', '')
            
            # Хорошее пояснение: длина > 50 символов, содержит объяснение
            if len(explanation) > 50 and ('почему' in explanation.lower() or 'так как' in explanation.lower()):
                good_explanations += 1
            elif len(explanation) > 30:
                good_explanations += 0.5
        
        score = good_explanations / max(len(self.questions), 1)
        
        return {
            "metric": "Качество пояснений",
            "good_explanations": good_explanations,
            "total": len(self.questions),
            "score": score
        }
    
    def calculate_all_metrics(self) -> Dict[str, Any]:
        """Рассчитывает все метрики качества"""
        
        metrics = {
            "test_title": self.test.get('test_title', ''),
            "total_questions": len(self.questions),
            "quality_checks": {}
        }
        
        # Выполняем все проверки
        checks = [
            self.check_question_count(),
            self.check_question_type(),
            self.check_options_count(),
            self.check_answer_uniqueness(),
            self.check_distractor_quality(),
            self.check_formula_usage(),
            self.check_difficulty_level(),
            self.check_explanation_quality()
        ]
        
        # Собираем результаты
        for check in checks:
            metrics["quality_checks"][check["metric"]] = check
        
        # Вычисляем итоговый Quality Score (0-1)
        weights = {
            "Количество вопросов": 0.10,
            "Тип вопросов": 0.10,
            "Количество вариантов": 0.10,
            "Однозначность ответа": 0.15,
            "Качество дистракторов": 0.20,
            "Использование формул": 0.15,
            "Уровень сложности": 0.10,
            "Качество пояснений": 0.10
        }
        
        total_score = 0
        for check in checks:
            metric_name = check["metric"]
            weight = weights.get(metric_name, 0.1)
            total_score += check["score"] * weight
        
        metrics["overall_quality_score"] = total_score
        
        # Оценка (отлично/хорошо/удовлетворительно/плохо)
        if total_score >= 0.9:
            metrics["grade"] = "Отлично"
        elif total_score >= 0.75:
            metrics["grade"] = "Хорошо"
        elif total_score >= 0.6:
            metrics["grade"] = "Удовлетворительно"
        else:
            metrics["grade"] = "Требует доработки"
        
        # Добавляем метаданные о времени и исходном файле
        metrics["metadata"] = {
            "evaluated_at": datetime.now().isoformat(),
            "source_test_file": str(self.test_path) if self.test_path else "unknown"
        }
        
        return metrics
    
    def print_report(self):
        """Выводит отчет о качестве теста"""
        metrics = self.calculate_all_metrics()
        
        
        print(f"ОТЧЕТ О КАЧЕСТВЕ ТЕСТА: {metrics['test_title']}")
        print(f"Всего вопросов: {metrics['total_questions']}")
        print(f"Итоговый Quality Score: {metrics['overall_quality_score']:.2%}")
        print(f"Оценка: {metrics['grade']}")
        
        for metric_name, check in metrics['quality_checks'].items():
            status = "Хорошо" if check.get('is_valid', check.get('score', 0) >= 0.7) else "!"
            print(f"{status} {metric_name}: {check['score']:.0%}")
            
            # Детали для критических метрик
            if metric_name == "Качество дистракторов" and check.get('issues'):
                print(f" Проблем: {len(check.get('issues', []))}")
        
        
    
    def save_results(self, output_path: str = None) -> str:
        """
        Сохраняет результаты метрик в JSON файл.
        
        Args:
            output_path: Путь для сохранения (если не указан, создается автоматически)
        
        Returns:
            Путь к сохраненному файлу
        """
        metrics = self.calculate_all_metrics()
        
        # Если путь не указан, создаем автоматически
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Получаем имя исходного теста
            if self.test_path:
                source_name = Path(self.test_path).stem
                output_path = f"quality_metrics_{source_name}_{timestamp}.json"
            else:
                output_path = f"quality_metrics_{timestamp}.json"
        
        # Сохраняем в JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        
        print(f"\n Результаты метрик сохранены в: {output_path}")
        return output_path


def analyze_test(test_path: str, save_results: bool = True) -> Dict[str, Any]:
    """
    Утилита для анализа теста из JSON файла с сохранением результатов.
    
    Args:
        test_path: Путь к файлу с тестом
        save_results: Сохранять ли результаты в JSON
    
    Returns:
        Словарь с метриками
    """
    with open(test_path, 'r', encoding='utf-8') as f:
        test_data = json.load(f)
    
    analyzer = TestQualityMetrics(test_data, test_path=test_path)
    analyzer.print_report()
    
    if save_results:
        output_path = analyzer.save_results()
        print(f"\n Результаты сохранены: {output_path}")
    
    return analyzer.calculate_all_metrics()


if __name__ == "__main__":
    import sys
    
    test_file = sys.argv[1] if len(sys.argv) > 1 else "test_result.json"
    save = len(sys.argv) <= 2 or sys.argv[2] != "--no-save"
    
    results = analyze_test(test_file, save_results=save)
    
    # Выводим итоговую оценку
    print(f"\n🎯 ИТОГОВАЯ ОЦЕНКА ТЕСТА: {results['grade']} (Quality Score: {results['overall_quality_score']:.2%})")
