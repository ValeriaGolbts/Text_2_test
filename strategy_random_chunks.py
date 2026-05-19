"""
strategy_random_chunks.py
Стратегия S1: случайный выбор чанков из оптимального диапазона.

Описание:
- Получает MIN/MAX из chunk_range_calculator.py
- Выбирает случайное количество чанков в диапазоне [MIN, MAX]
- Извлекает случайные чанки из pipeline JSON
- Отправляет в GigaChat для генерации теста

Автор: Для магистерской работы
"""

import json
import asyncio
import sys
import random
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from api_client_b2b import GigaChatB2BClient
from config import config
from chunk_range_calculator import get_chunk_range


class StrategyRandomChunks:
    """
    Стратегия S1: случайный выбор чанков из оптимального диапазона.
    
    Особенности:
    - Количество чанков выбирается случайно в диапазоне [MIN, MAX]
    - Сами чанки выбираются случайно из всего набора
    - Можно зафиксировать seed для воспроизводимости
    """
    
    def __init__(self, random_seed: Optional[int] = None):
        """
        Args:
            random_seed: seed для воспроизводимости (если нужны повторяемые результаты)
        """
        self.client = GigaChatB2BClient()
        self.random_seed = random_seed
        if random_seed is not None:
            random.seed(random_seed)
        print(f"Инициализирована стратегия S1 (случайные чанки)")
        print(f"  • Random seed: {random_seed if random_seed else 'не задан'}")
    
    def get_chunk_range(self, json_path: str) -> Tuple[int, int]:
        """
        Получает диапазон чанков из chunk_range_calculator.py.
        
        Returns:
            (max_chunks, min_chunks)
        """
        try:
            max_chunks, min_chunks = get_chunk_range(json_path, verbose=False)
            print(f"  • Диапазон от chunk_range_calculator: MIN={min_chunks}, MAX={max_chunks}")
            return max_chunks, min_chunks
        except Exception as e:
            print(f"  • Ошибка получения диапазона: {e}")
            print(f"  • Использую значения по умолчанию: MIN=3, MAX=8")
            return 8, 3
    
    def select_random_chunks(self, chunks: List[Dict], min_chunks: int, max_chunks: int) -> Tuple[List[Dict], int, List[int]]:
        """
        Выбирает случайное количество чанков из диапазона и случайные чанки.
        
        Args:
            chunks: Список всех чанков
            min_chunks: Минимальное количество чанков
            max_chunks: Максимальное количество чанков
        
        Returns:
            (selected_chunks, actual_count, selected_indices)
        """
        total_available = len(chunks)
        
        # 1. Выбираем случайное количество чанков в диапазоне
        if min_chunks >= max_chunks:
            k = min_chunks
        else:
            k = random.randint(min_chunks, max_chunks)
        
        # 2. Не больше, чем всего чанков
        k = min(k, total_available)
        
        # 3. Выбираем случайные индексы
        all_indices = list(range(total_available))
        selected_indices = random.sample(all_indices, k) if k <= total_available else all_indices
        
        # 4. Получаем чанки по индексам
        selected_chunks = [chunks[i] for i in selected_indices]
        
        print(f"  • Выбрано {k} чанков из {total_available}")
        print(f"  • Индексы: {selected_indices[:5]}..." if len(selected_indices) > 5 else f"  • Индексы: {selected_indices}")
        
        return selected_chunks, k, selected_indices
    
    def extract_text_from_chunks(self, chunks: List[Dict]) -> List[str]:
        """Извлекает текст из выбранных чанков"""
        texts = []
        for chunk in chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        return texts
    
    def get_formulas_from_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """Извлекает формулы из выбранных чанков (для статистики)"""
        formulas = []
        for chunk in chunks:
            chunk_formulas = chunk.get('formulas', [])
            for f in chunk_formulas:
                formulas.append({
                    'chunk_id': chunk.get('id'),
                    'original': f.get('original', ''),
                    'normalized': f.get('normalized', ''),
                    'type': f.get('type', '')
                })
        return formulas
    
    def create_prompt(self, texts: List[str], 
                      num_questions: int = 10,
                      difficulty: str = "medium",
                      question_types: str = "mixed") -> str:
        """
        Создает промпт для генерации теста.
        
        Args:
            texts: Список текстов чанков
            num_questions: Количество вопросов
            difficulty: Сложность (easy, medium, hard)
            question_types: Типы вопросов (open, closed, mixed)
        """
        
        # Объединяем тексты с разделителями
        context = "\n\n---\n\n".join(texts)
        
        # Определяем типы вопросов
        if question_types == "open":
            types_instruction = "ТОЛЬКО открытые вопросы (пользователь вводит ответ)"
        elif question_types == "closed":
            types_instruction = "ТОЛЬКО закрытые вопросы (4 варианта ответа, один правильный)"
        else:  # mixed
            types_instruction = "СМЕШАННЫЙ ТИП: 50% открытых вопросов, 50% закрытых (с 4 вариантами ответа)"
        
        # Сложность
        difficulty_map = {
            "easy": "Простые вопросы на базовое понимание определений и простых формул",
            "medium": "Средние вопросы на применение формул и понимание связей между концепциями",
            "hard": "Сложные вопросы на анализ, синтез и решение нетривиальных задач"
        }
        
        # Шаблон JSON выносим отдельно
        json_example = '''{
    "test_title": "Название теста (по теме материала)",
    "subject": "Предмет/тема",
    "difficulty": "medium",
    "num_questions": 5,
    "questions": [
        {
            "id": 1,
            "question": "Текст вопроса",
            "type": "closed",
            "options": ["Вариант А", "Вариант Б", "Вариант В", "Вариант Г"],
            "correct_answer": "Вариант А",
            "explanation": "Краткое пояснение"
        },
        {
            "id": 2,
            "question": "Текст открытого вопроса",
            "type": "open",
            "expected_answer": "Ожидаемый ответ или ключевые моменты",
            "explanation": "Пояснение"
        }
    ]
}'''
        
        prompt = f"""Ты — эксперт по генерации учебных тестов для студентов магистратуры по точным наукам.

ПАРАМЕТРЫ ТЕСТА:
- Количество вопросов: {num_questions}
- Сложность: {difficulty} - {difficulty_map.get(difficulty, difficulty_map['medium'])}
- Типы вопросов: {types_instruction}

ИСХОДНЫЙ МАТЕРИАЛ (случайно выбранные фрагменты лекции):
{context}

ТРЕБОВАНИЯ К ТЕСТУ:
1. Все вопросы должны быть строго по содержанию предоставленного материала
2. Не придумывай факты, которых нет в тексте
3. Вопросы должны проверять понимание ключевых концепций и формул
4. Используй математические обозначения и формулы там, где это уместно
5. Для закрытых вопросов создай 4 варианта, один правильный
6. Для открытых вопросов ожидай развернутый ответ

ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без пояснений). Пример:
{json_example}

ВАЖНО: Верни ТОЛЬКО JSON, без дополнительного текста перед или после."""
        
        return prompt
    
    async def generate_test(self, 
                           json_path: str,
                           num_questions: int = 10,
                           difficulty: str = "medium",
                           question_types: str = "mixed",
                           save_result: bool = True,
                           verbose: bool = True) -> Dict[str, Any]:
        """
        Основной метод: случайный выбор чанков и генерация теста.
        
        Args:
            json_path: Путь к output.json
            num_questions: Количество вопросов в тесте
            difficulty: Сложность (easy, medium, hard)
            question_types: Типы вопросов (open, closed, mixed)
            save_result: Сохранять ли результат в файл
            verbose: Показывать ли подробный вывод
        
        Returns:
            Результат с тестом и метаданными
        """
        
        print("\n" + "="*60)
        print("СТРАТЕГИЯ S1: СЛУЧАЙНЫЙ ВЫБОР ЧАНКОВ")
        print("="*60)
        
        # 1. Загружаем JSON
        if verbose:
            print(f"\n Загрузка: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            pipeline_data = json.load(f)
        
        chunks = pipeline_data.get('chunks', [])
        if not chunks:
            return {"error": "Нет чанков в файле"}
        
        total_chunks = len(chunks)
        if verbose:
            print(f" Всего чанков: {total_chunks}")
        
        # 2. Получаем диапазон
        max_chunks, min_chunks = self.get_chunk_range(json_path)
        
        # 3. Выбираем случайные чанки
        selected_chunks, actual_k, selected_indices = self.select_random_chunks(
            chunks, min_chunks, max_chunks
        )
        
        # 4. Извлекаем текст и формулы
        texts = self.extract_text_from_chunks(selected_chunks)
        formulas = self.get_formulas_from_chunks(selected_chunks)
        
        if verbose:
            print(f"\n Извлечено текста: {len(texts)} блоков")
            print(f" Формул в выбранных чанках: {len(formulas)}")
        
        # 5. Получаем метаданные
        metadata = {
            'source_file': pipeline_data.get('source_file', 'unknown'),
            'process_id': pipeline_data.get('process_id', 'unknown'),
            'processed_at': pipeline_data.get('processed_at', 'unknown'),
            'total_chunks_original': total_chunks,
            'chunks_used': actual_k,
            'chunk_indices': selected_indices,
            'chunk_ids': [c.get('id') for c in selected_chunks],
            'total_formulas_in_chunks': len(formulas),
            'strategy': 'S1_random',
            'strategy_params': {
                'min_chunks': min_chunks,
                'max_chunks': max_chunks,
                'random_seed': self.random_seed
            },
            'user_params': {
                'num_questions': num_questions,
                'difficulty': difficulty,
                'question_types': question_types
            }
        }
        
        # 6. Создаем промпт
        prompt = self.create_prompt(texts, num_questions, difficulty, question_types)
        
        if verbose:
            print(f"\n Отправка в GigaChat")
            print(f"  • Вопросов: {num_questions}")
            print(f"  • Сложность: {difficulty}")
            print(f"  • Типы: {question_types}")
            print(f"  • Длина промпта: {len(prompt)} символов")
        
        # 7. Отправляем запрос
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=4096,
                temperature=0.7
            )
            
            if verbose:
                print(f"✅ Получен ответ от GigaChat")
            
            # 8. Извлекаем JSON
            content = response['choices'][0]['message']['content']
            
            # Очистка от маркеров кода
            import re
            json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Пробуем найти любой JSON объект
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    json_str = content
            
            # Парсим
            try:
                test_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                if verbose:
                    print(f"⚠️ Ошибка парсинга JSON: {e}")
                test_result = {"raw_response": content, "questions": [], "parse_error": str(e)}
            
            # 9. Добавляем метаданные
            test_result['strategy_metadata'] = metadata
            test_result['pipeline_metadata'] = {
                'source_file': pipeline_data.get('source_file'),
                'process_id': pipeline_data.get('process_id')
            }
            
            # 10. Сохраняем результат
            if save_result:
                output_path = self.save_result(test_result, strategy_name="S1_random")
                test_result['saved_to'] = output_path
            
            return test_result
            
        except Exception as e:
            print(f" Ошибка: {e}")
            return {"error": str(e), "strategy_metadata": metadata}
    
    def save_result(self, result: Dict[str, Any], strategy_name: str = "S1_random") -> str:
        """Сохраняет результат в JSON файл"""
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Получаем информацию для имени файла
        source = result.get('pipeline_metadata', {}).get('source_file', 'unknown')
        source_name = Path(source).stem if source else 'unknown'
        
        output_path = f"test_result_{strategy_name}_{source_name}_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результат сохранен: {output_path}")
        return output_path


async def main():
    """Основная функция для тестирования стратегии S1"""
    
    # Путь к JSON файлу
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    # Проверяем существование
    if not Path(json_file).exists():
        print(f" Файл не найден: {json_file}")
        
        # Ищем в текущей папке
        current_dir = Path(__file__).parent
        possible_files = list(current_dir.glob("*.json"))
        if possible_files:
            print(f"\n🔍 Найденные JSON файлы:")
            for f in possible_files:
                print(f"  • {f}")
            json_file = str(possible_files[0])
            print(f"\n Использую: {json_file}")
        else:
            return
    
    # Создаем стратегию (фиксируем seed для воспроизводимости)
    strategy = StrategyRandomChunks(random_seed=42)
    
    # Параметры эксперимента
    params = {
        "num_questions": 10,
        "difficulty": "medium",
        "question_types": "mixed"
    }
    
    # Генерируем тест
    result = await strategy.generate_test(
        json_path=json_file,
        num_questions=params["num_questions"],
        difficulty=params["difficulty"],
        question_types=params["question_types"],
        save_result=True,
        verbose=True
    )
    
    # Выводим результат
    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТ ТЕСТА")
    print("="*60)
    
    if 'error' in result:
        print(f"Ошибка: {result['error']}")
    else:
        print(f"Название: {result.get('test_title', 'Не указано')}")
        print(f"Предмет: {result.get('subject', 'Не указан')}")
        print(f"Сложность: {result.get('difficulty', 'Не указана')}")
        print(f"Вопросов: {len(result.get('questions', []))}")
        
        # Статистика по чанкам
        meta = result.get('strategy_metadata', {})
        print(f"\nСтатистика стратегии:")
        print(f" Использовано чанков: {meta.get('chunks_used', '?')} из {meta.get('total_chunks_original', '?')}")
        print(f" Формул в чанках: {meta.get('total_formulas_in_chunks', '?')}")
        print(f" Диапазон: [{meta.get('strategy_params', {}).get('min_chunks', '?')}, {meta.get('strategy_params', {}).get('max_chunks', '?')}]")
        
        # Показываем первый вопрос
        questions = result.get('questions', [])
        if questions:
            print(f"\n Пример вопроса:")
            q = questions[0]
            print(f"  {q.get('question', '')[:150]}...")
            if q.get('type') == 'closed':
                print(f"  Варианты: {q.get('options', [])}")
            print(f"  Ответ: {q.get('correct_answer', q.get('expected_answer', ''))[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
