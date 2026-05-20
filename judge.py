"""
judge.py
Скрипт для экспертной оценки тестов через LLM-as-judge.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from expert_evaluation_llm import LLMExpertEvaluator
from api_client_b2b import GigaChatB2BClient


async def main():
    """Основная асинхронная функция"""
    
    # Инициализация
    llm_client = GigaChatB2BClient()
    evaluator = LLMExpertEvaluator(llm_client, temperature=0.2)
    
    # Список тестов для оценки (замените на ваши файлы)
    test_files = [
        "test_result_S1_random_lecture_20260519.json",
        "test_result_S2_key_terms_lecture_20260520.json",
        "test_result_S3_semantic_lecture_20260520.json",
        "test_result_S4_hybrid_lecture_20260520.json",
    ]
    
    # Фильтруем существующие файлы
    existing_tests = [f for f in test_files if Path(f).exists()]
    
    if not existing_tests:
        print("❌ Нет файлов с тестами для оценки")
        print(f"   Искал: {test_files}")
        
        # Показываем все JSON файлы в папке
        json_files = list(Path(".").glob("*.json"))
        if json_files:
            print("\n📁 Доступные JSON файлы:")
            for f in json_files:
                print(f"   • {f}")
        return
    
    print(f"📂 Найдено тестов: {len(existing_tests)}")
    for f in existing_tests:
        print(f"   • {f}")
    
    # Оценка всех тестов
    results = await evaluator.evaluate_multiple("output.json", existing_tests)
    
    # Вывод таблицы сравнения
    evaluator.print_comparison_table(results)
    
    # Дополнительно: проверка консистентности на первом тесте (опционально)
    if existing_tests:
        print("\n" + "=" * 60)
        print("ПРОВЕРКА КОНСИСТЕНТНОСТИ LLM-as-judge")
        print("=" * 60)
        
        consistency = await evaluator.evaluate_with_consistency_check(
            "output.json", 
            existing_tests[0], 
            num_runs=3
        )
        
        print(f"\n📊 Consistency score: {consistency['consistency_score']:.2%}")
        if consistency['consistency_score'] >= 0.8:
            print("   ✅ LLM стабилен в оценках")
        elif consistency['consistency_score'] >= 0.6:
            print("   ⚠️ LLM умеренно стабилен")
        else:
            print("   ❌ LLM нестабилен — рекомендуется усреднение")


if __name__ == "__main__":
    # Запуск асинхронной функции
    asyncio.run(main())
