"""
expert_evaluation_llm.py
Экспертная оценка качества тестов через LLM (без участия человека).

Подход: GigaChat выступает в роли эксперта-педагога.
Это полностью автоматический и воспроизводимый метод.

Автор: Для магистерской работы
"""

import json
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class LLMExpertEvaluator:
    """
    Класс для автоматической экспертной оценки тестов через LLM.
    
    LLM оценивает по 5 критериям (каждый от 1 до 5):
    1. Фактическая точность (accuracy)
    2. Соответствие исходному материалу (grounding)
    3. Осмысленность вопросов (meaningfulness)
    4. Разнообразие (diversity)
    5. Полезность для обучения (usefulness)
    
    Также вычисляются консистентность и надежность оценок.
    """
    
    def __init__(self, llm_client, temperature: float = 0.2):
        """
        Args:
            llm_client: Клиент для LLM (должен иметь метод send_request)
            temperature: Температура для консистентности (низкая = стабильные оценки)
        """
        self.llm_client = llm_client
        self.temperature = temperature
        
        # Критерии оценки
        self.criteria = {
            "accuracy": {
                "name": "Фактическая точность",
                "description": "Нет ли ошибок в вопросах и ответах?",
                "scale": """5=Абсолютно корректно: все утверждения верны, формулы правильно записаны
                          4=Незначительные недочёты: 1-2 мелкие неточности, не влияющие на суть
                          3=Средний уровень: 3-4 ошибки или одна существенная ошибка в формуле
                          2=Много ошибок: 5+ ошибок, некоторые формулы неверны
                          1=Критически плохо: массовые ошибки, тест нельзя использовать""",
                "check_points": [
                    "Проверь каждую формулу на корректность LaTeX",
                    "Проверь математические утверждения на истинность",
                    "Убедись, что правильный ответ действительно верен"
                ]
            },
            "grounding": {
                "name": "Соответствие материалу",
                "description": "Можно ли найти ответы в исходной лекции?",
                "scale": """5=Полное соответствие: все ответы явно присутствуют в тексте лекции
4=Хорошее соответствие: 90% ответов есть в тексте
3=Среднее соответствие: 70-80% ответов можно найти в тексте
2=Слабое соответствие: только 50% ответов есть в тексте
1=Отсутствие связи: ответов нет в лекции, LLM сгенерировала выдумки""",
                "check_points": [
                    "Для каждого вопроса проверь, есть ли ответ в исходном тексте",
                    "Отметь вопросы, где LLM добавила информацию из своего знания"
                ]
            },
            "meaningfulness": {
                "name": "Осмысленность",
                "description": "Проверяют ли вопросы понимание, а не просто факты?",
                "scale": "1=тривиальные вопросы, 5=глубокие вопросы на понимание"
            },
            "diversity": {
                "name": "Разнообразие",
                "description": "Покрывают ли вопросы разные темы/разделы?",
                "scale": """5=Отличное разнообразие: охвачены все ключевые темы, разные типы заданий
4=Хорошее разнообразие: покрыто 80% тем, есть вариативность
3=Среднее разнообразие: покрыто 60% тем, вопросы однотипны
2=Низкое разнообразие: покрыто 40% тем, повторяются одни и те же концепции
1=Отсутствие разнообразия: все вопросы из одного параграфа/темы""",
                "check_points": [
                    "Охвачены ли все ключевые разделы лекции?",
                    "Есть ли вопросы разной сложности?",
                    "Повторяются ли похожие вопросы?"
                ]
            },
            "usefulness": {
                "name": "Полезность",
                "description": "Насколько тест полезен для проверки знаний студентов?",
                "scale": """5=Очень полезен: отлично выявляет пробелы в знаниях, подходит для экзамена
4=Полезен: хорошо проверяет понимание, можно использовать для контроля
3=Умеренно полезен: базовый уровень, выявляет только явные пробелы
2=Мало полезен: слишком простой или слишком сложный, не диагностирует проблемы
1=Бесполезен: не соответствует материалу или тривиален""",
                "check_points": [
                    "Сможет ли преподаватель оценить понимание студента по этому тесту?",
                    "Выявляет ли тест типичные ошибки студентов?",
                    "Соответствует ли уровень сложности заявленному?"
                ]
            }
        }
    
    def _extract_chunks_text(self, chunks_data: Dict, max_chunks: int = 5) -> str:
        """Извлекает текст из первых N чанков для контекста"""
        chunks = chunks_data.get('chunks', [])
        selected = chunks[:max_chunks]
        texts = []
        for c in selected:
            text = c.get('processed_text', '')
            if text:
                # Ограничиваем длину каждого чанка
                texts.append(text[:1500])
        return "\n\n---\n\n".join(texts)
    
    def _extract_test_text(self, test_result: Dict) -> str:
        """Извлекает тест в читаемом формате для LLM"""
        questions = test_result.get('questions', [])
        if not questions:
            return "Нет вопросов для оценки"
        
        output = []
        for i, q in enumerate(questions, 1):
            output.append(f"[Вопрос {i}]")
            output.append(f"Текст: {q.get('question', '')}")
            
            if q.get('type') == 'closed':
                output.append(f"Тип: закрытый")
                output.append(f"Варианты: {', '.join(q.get('options', []))}")
                output.append(f"Правильный ответ: {q.get('correct_answer', '')}")
            else:
                output.append(f"Тип: открытый")
                output.append(f"Ожидаемый ответ: {q.get('expected_answer', '')}")
            
            output.append(f"Пояснение: {q.get('explanation', '')}")
            output.append("")
        
        return "\n".join(output)
    
    def _create_judge_prompt(self, chunks_text: str, test_text: str) -> str:
        """Создает промпт для LLM-эксперта"""
        
        criteria_text = "\n".join([
            f"**{i+1}. {c['name']}** (1-5): {c['description']} — {c['scale']}"
            for i, c in enumerate(self.criteria.values())
        ])
        
        return f"""Ты — строгий эксперт по педагогике и методике преподавания технических дисциплин в вузе. Твоя задача — максимально объективно оценить качество теста.

## КРИТЕРИИ ОЦЕНКИ (каждый от 1 до 5, где 5 — отлично):

{criteria_text}

## ИСХОДНЫЙ МАТЕРИАЛ ЛЕКЦИИ (фрагменты):
{chunks_text}

## ОЦЕНИВАЕМЫЙ ТЕСТ:
{test_text}

## ИНСТРУКЦИЯ:
1. Внимательно прочитай исходный материал и тест
2. Поставь оценку от 1 до 5 по каждому критерию
3. Добавь краткий комментарий по каждому критерию (что хорошо, что можно улучшить)
4. Поставь общую оценку (от 1 до 5) и напиши общий комментарий

## ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без пояснений до и после):
{{
    "accuracy": {{"score": 1-5, "comment": "комментарий"}},
    "grounding": {{"score": 1-5, "comment": "комментарий"}},
    "meaningfulness": {{"score": 1-5, "comment": "комментарий"}},
    "diversity": {{"score": 1-5, "comment": "комментарий"}},
    "usefulness": {{"score": 1-5, "comment": "комментарий"}},
    "overall_score": 1-5,
    "overall_comment": "общий комментарий по тесту"
}}"""
    
    async def evaluate_single(self, 
                              chunks_path: str, 
                              test_path: str,
                              verbose: bool = True) -> Dict[str, Any]:
        """
        Оценивает один тест через LLM.
        
        Args:
            chunks_path: Путь к output.json (исходные чанки)
            test_path: Путь к test_result.json (сгенерированный тест)
            verbose: Показывать ли подробный вывод
        
        Returns:
            Словарь с оценками по критериям
        """
        print(f"\n  📊 Оценка теста: {Path(test_path).name}")
        
        # Загрузка данных
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        with open(test_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
        
        # Извлекаем текст
        chunks_text = self._extract_chunks_text(chunks_data, max_chunks=5)
        test_text = self._extract_test_text(test_data)
        
        # Создаем промпт
        prompt = self._create_judge_prompt(chunks_text, test_text)
        
        # Отправляем запрос
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.llm_client.send_request(
                messages=messages,
                max_tokens=2000,
                temperature=self.temperature
            )
            
            content = response['choices'][0]['message']['content']
            
            # Извлекаем JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                evaluation = json.loads(json_str)
            else:
                evaluation = {"error": "Не удалось извлечь JSON", "raw_response": content}
            
            # Добавляем метаданные
            evaluation['metadata'] = {
                'chunks_file': str(chunks_path),
                'test_file': str(test_path),
                'evaluation_method': 'LLM-as-judge',
                'evaluated_at': datetime.now().isoformat(),
                'temperature': self.temperature
            }
            
            if verbose:
                scores = [evaluation.get(k, {}).get('score', 0) for k in self.criteria.keys()]
                avg_score = sum(scores) / len(scores) if scores else 0
                print(f"    📈 Средняя оценка: {avg_score:.1f}/5 | Общая: {evaluation.get('overall_score', '?')}/5")
            
            return evaluation
            
        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
            return {"error": str(e), "test_file": str(test_path)}
    
    async def evaluate_multiple(self, 
                                chunks_path: str, 
                                test_paths: List[str],
                                save_results: bool = True,
                                verbose: bool = True) -> Dict[str, Any]:
        """
        Оценивает несколько тестов (например, для сравнения стратегий).
        
        Args:
            chunks_path: Путь к output.json
            test_paths: Список путей к test_result.json
            save_results: Сохранять ли результаты в файл
            verbose: Показывать ли подробный вывод
        
        Returns:
            Словарь с оценками для каждого теста
        """
        results = {}
        
      
        print("ЭКСПЕРТНАЯ ОЦЕНКА ТЕСТОВ (LLM-as-judge)")
        print(f"Тестов для оценки: {len(test_paths)}")
        
        for test_path in test_paths:
            evaluation = await self.evaluate_single(chunks_path, test_path, verbose=verbose)
            
            # Извлекаем ключевые метрики
            strategy_name = Path(test_path).stem.replace('test_result_', '').replace('_lecture', '')
            results[strategy_name] = {
                'test_file': test_path,
                'scores': {k: evaluation.get(k, {}).get('score', 0) for k in self.criteria.keys()},
                'overall_score': evaluation.get('overall_score', 0),
                'comments': {k: evaluation.get(k, {}).get('comment', '') for k in self.criteria.keys()},
                'overall_comment': evaluation.get('overall_comment', ''),
                'metadata': evaluation.get('metadata', {})
            }
        
        # Добавляем сводную таблицу
        results['summary'] = self._create_summary_table(results)
        
        if save_results:
            output_path = f"expert_evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Результаты сохранены в: {output_path}")
        
        return results
    
    def _create_summary_table(self, results: Dict) -> Dict:
        """Создает сводную таблицу для сравнения стратегий"""
        summary = {
            "strategies": [],
            "criteria_averages": {},
            "ranking": []
        }
        
        # Собираем данные по стратегиям
        for strategy, data in results.items():
            if strategy == 'summary':
                continue
            
            summary["strategies"].append({
                "name": strategy,
                "accuracy": data['scores'].get('accuracy', 0),
                "grounding": data['scores'].get('grounding', 0),
                "meaningfulness": data['scores'].get('meaningfulness', 0),
                "diversity": data['scores'].get('diversity', 0),
                "usefulness": data['scores'].get('usefulness', 0),
                "overall_score": data['overall_score'],
                "average_score": sum(data['scores'].values()) / len(data['scores'])
            })
        
        # Сортируем по общей оценке
        summary["ranking"] = sorted(
            summary["strategies"],
            key=lambda x: x['average_score'],
            reverse=True
        )
        
        # Средние по критериям
        for criterion in ['accuracy', 'grounding', 'meaningfulness', 'diversity', 'usefulness']:
            scores = [s[criterion] for s in summary["strategies"]]
            summary["criteria_averages"][criterion] = sum(scores) / len(scores) if scores else 0
        
        return summary
    
    async def evaluate_with_consistency_check(self,
                                               chunks_path: str,
                                               test_path: str,
                                               num_runs: int = 3,
                                               verbose: bool = True) -> Dict[str, Any]:
        """
        Оценивает тест несколько раз для проверки консистентности LLM.
        
        Args:
            chunks_path: Путь к output.json
            test_path: Путь к test_result.json
            num_runs: Количество запусков для проверки
            verbose: Показывать ли подробный вывод
        
        Returns:
            Оценки со статистикой (среднее, std, min, max)
        """
        print(f"\n🔬 Проверка консистентности LLM-as-judge ({num_runs} запусков)")
        
        all_evaluations = []
        
        for run in range(num_runs):
            print(f"  Запуск {run + 1}/{num_runs}...")
            evaluation = await self.evaluate_single(chunks_path, test_path, verbose=False)
            
            scores = {
                'accuracy': evaluation.get('accuracy', {}).get('score', 0),
                'grounding': evaluation.get('grounding', {}).get('score', 0),
                'meaningfulness': evaluation.get('meaningfulness', {}).get('score', 0),
                'diversity': evaluation.get('diversity', {}).get('score', 0),
                'usefulness': evaluation.get('usefulness', {}).get('score', 0),
                'overall': evaluation.get('overall_score', 0)
            }
            all_evaluations.append(scores)
        
        # Статистика
        import statistics
        
        result = {
            'test_file': test_path,
            'num_runs': num_runs,
            'runs': all_evaluations,
            'statistics': {}
        }
        
        for criterion in ['accuracy', 'grounding', 'meaningfulness', 'diversity', 'usefulness', 'overall']:
            scores = [e[criterion] for e in all_evaluations]
            result['statistics'][criterion] = {
                'mean': statistics.mean(scores),
                'std': statistics.stdev(scores) if len(scores) > 1 else 0,
                'min': min(scores),
                'max': max(scores),
                'range': max(scores) - min(scores)
            }
        
        # Оценка консистентности
        avg_std = statistics.mean([result['statistics'][c]['std'] for c in result['statistics']])
        result['consistency_score'] = 1.0 - min(1.0, avg_std / 2)  # 0-1, чем выше, тем консистентнее
        
        if verbose:
            print(f"\n📊 Результаты консистентности:")
            print(f"   Среднее отклонение: {avg_std:.2f}")
            print(f"   Consistency score: {result['consistency_score']:.2%}")
            if avg_std <= 0.5:
                print(f"    LLM стабилен в оценках")
            elif avg_std <= 1.0:
                print(f"    LLM умеренно стабилен")
            else:
                print(f"    LLM нестабилен — рекомендуется усреднение по нескольким запускам")
        
        return result
    
    def print_comparison_table(self, results: Dict):
        """Выводит таблицу сравнения стратегий"""
        if 'summary' not in results:
            print("Нет данных для сравнения")
            return
        
        
        print(" СРАВНЕНИЕ СТРАТЕГИЙ ПО ЭКСПЕРТНОЙ ОЦЕНКЕ (LLM-as-judge)")
        print("=" * 80)
        
        # Заголовок
        print(f"{'Стратегия':<20} | {'Точн':<5} | {'Соотв':<5} | {'Смысл':<5} | {'Разнооб':<5} | {'Полезн':<5} | {'Средн':<5} | {'Итог':<5}")
        print("-" * 80)
        
        for strategy in results['summary']['ranking']:
            name = strategy['name'][:18]
            print(f"{name:<20} | {strategy['accuracy']:<5} | {strategy['grounding']:<5} | {strategy['meaningfulness']:<5} | {strategy['diversity']:<5} | {strategy['usefulness']:<5} | {strategy['average_score']:<5.1f} | {strategy['overall_score']:<5}")
        
        print("-" * 80)
        print(f"{'СРЕДНЕЕ':<20} | {results['summary']['criteria_averages']['accuracy']:<5.1f} | {results['summary']['criteria_averages']['grounding']:<5.1f} | {results['summary']['criteria_averages']['meaningfulness']:<5.1f} | {results['summary']['criteria_averages']['diversity']:<5.1f} | {results['summary']['criteria_averages']['usefulness']:<5.1f}")
        print("=" * 80)
        
        # Лучшая стратегия
        best = results['summary']['ranking'][0]
        print(f"\n ЛУЧШАЯ СТРАТЕГИЯ: {best['name']}")
        print(f"   Средняя оценка: {best['average_score']:.1f}/5")
        print(f"   Общая оценка: {best['overall_score']}/5")


async def main():
    """Пример использования"""
    from api_client_b2b import GigaChatB2BClient
    
    # Инициализация
    llm_client = GigaChatB2BClient()
    evaluator = LLMExpertEvaluator(llm_client, temperature=0.2)
    
    # Пример: оценка одного теста
    # result = await evaluator.evaluate_single("output.json", "test_result.json")
    # print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Пример: оценка нескольких тестов (стратегий)
    test_files = [
        "test_result_S1_random_lecture_20260519.json",
        "test_result_S2_key_terms_lecture_20260520.json",
        "test_result_S3_semantic_lecture_20260520.json",
        "test_result_S4_hybrid_lecture_20260520.json",
    ]
    
    # Фильтруем существующие файлы
    existing_tests = [f for f in test_files if Path(f).exists()]
    
    if existing_tests:
        results = await evaluator.evaluate_multiple("output.json", existing_tests)
        evaluator.print_comparison_table(results)
    else:
        print("Нет файлов с тестами для оценки")
        
        # Проверка консистентности на одном тесте
        if Path("test_result.json").exists():
            consistency = await evaluator.evaluate_with_consistency_check("output.json", "test_result.json")
            print(f"Consistency score: {consistency['consistency_score']:.2%}")


if __name__ == "__main__":
    asyncio.run(main())
