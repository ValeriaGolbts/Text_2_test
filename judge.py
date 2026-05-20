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
        "s5_1.json",
        "s5_2.json",
        "s5_3.json",
        "s5_4.json",
    ]
    
    # Фильтруем существующие файлы
    existing_tests = [f for f in test_files if Path(f).exists()]
    
    if not existing_tests:
        print(" Нет файлов с тестами для оценки")
        print(f"   Искал: {test_files}")
        
        # Показываем все JSON файлы в папке
        json_files = list(Path(".").glob("*.json"))
        if json_files:
            print("\n Доступные JSON файлы:")
            for f in json_files:
                print(f"   • {f}")
        return
    
    print(f" Найдено тестов: {len(existing_tests)}")
    for f in existing_tests:
        print(f"   • {f}")
    
    # Оценка всех тестов
    results = await evaluator.evaluate_multiple("output.json", existing_tests)
    
    # Вывод таблицы сравнения
    evaluator.print_comparison_table(results)
    
    


if __name__ == "__main__":
    # Запуск асинхронной функции
    asyncio.run(main())
