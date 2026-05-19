"""
Обработка JSON файла от pipeline через GigaChat B2B клиент
с автоматическим отбором чанков по стратегии 80% покрытия
"""
import json
import asyncio
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from api_client_b2b import GigaChatB2BClient
from config import config

# Импортируем функции расчёта чанков
from chunk_range_calculator import (
    analyze_chunks_detailed,
    calculate_max_chunks,
    calculate_min_chunks,
    MODEL_CONFIG,
    TOTAL_PROMPT_OVERHEAD
)


class PipelineJSONProcessor:
    """Обработчик JSON файлов от pipeline с отправкой в GigaChat"""
    
    def __init__(self):
        self.client = GigaChatB2BClient()
        print(f"✅ Инициализирован B2B клиент")
    
    def load_pipeline_json(self, json_path: str) -> Dict[str, Any]:
        """Загружает JSON файл от pipeline"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📁 Загружен JSON: {json_path}")
            return data
        except Exception as e:
            print(f"❌ Ошибка загрузки JSON: {e}")
            return {}
    
    def select_chunks_80_percent(self, pipeline_data: Dict[str, Any]) -> Tuple[List[Dict], Dict]:
        """
        Отбирает чанки по стратегии 80% покрытия материала.
        
        Алгоритм:
        1. Анализирует чанки через analyze_chunks_detailed()
        2. Рассчитывает max_chunks и min_chunks НАПРЯМУЮ (без get_chunk_range)
        3. Сортирует чанки по информативности (формулы + ключевые термины)
        4. Отбирает чанки, пока не покрыто 80% формул и 80% терминов
        5. Не превышает max_chunks (ограничение контекстного окна)
        
        Returns:
            (selected_chunks, selection_info)
        """
        chunks = pipeline_data.get('chunks', [])
        
        if not chunks:
            return [], {"error": "Нет чанков для отбора"}
        
        # 1. Анализируем все чанки
        stats = analyze_chunks_detailed(chunks)
        
        # 2. Рассчитываем max_chunks и min_chunks НАПРЯМУЮ
        # (без вызова get_chunk_range, которому нужен путь к файлу)
        max_chunks, max_details = calculate_max_chunks(stats)
        min_chunks, min_details = calculate_min_chunks(stats)
        
        print(f"\n📊 ДИАПАЗОН ЧАНКОВ:")
        print(f"  • Максимум (влезает в контекст): {max_chunks}")
        print(f"  • Минимум (покрытие материала): {min_chunks}")
        print(f"  • Всего чанков в файле: {stats['total_chunks']}")
        print(f"  • Средний размер чанка: {stats['avg_chunk_tokens']} токенов")
        print(f"  • Общий объём: {stats['total_tokens']:,} токенов")
        
        # 3. Определяем целевые показатели (80% от максимума)
        total_formulas = stats["total_formulas"]
        
        # Собираем ВСЕ уникальные термины из всех чанков
        all_terms = set()
        for chunk_data in stats["chunk_data"]:
            # Получаем оригинальный чанк по sequence
            chunk_original = chunks[chunk_data["sequence"]]
            all_terms.update(
                chunk_original.get("metadata", {}).get("key_terms", [])
            )
        total_unique_terms = len(all_terms)
        
        # Цели: 80% от максимума
        target_formulas = max(1, int(total_formulas * 0.8))
        target_terms = max(1, int(total_unique_terms * 0.8))
        
        print(f"\n🎯 ЦЕЛИ ПОКРЫТИЯ (80%):")
        print(f"  • Формул: {target_formulas} из {total_formulas}")
        print(f"  • Терминов: {target_terms} из {total_unique_terms}")
        
        # 4. Сортируем чанки по информативности
        # Используем уже отсортированные данные из stats
        chunks_sorted = stats["chunk_data_sorted"]
        
        # 5. Ползучее накопление до 80%
        selected = []
        formulas_covered = 0
        terms_covered = set()
        
        print(f"\n🔄 ПРОЦЕСС ОТБОРА:")
        
        for i, chunk_data in enumerate(chunks_sorted, 1):
            if len(selected) >= max_chunks:
                print(f"  ⚠ Достигнут лимит max_chunks ({max_chunks})")
                break
            
            # Получаем оригинальный чанк по индексу
            original_chunk = chunks[chunk_data["sequence"]]
            selected.append(original_chunk)
            
            formulas_covered += chunk_data["formula_count"]
            
            # Извлекаем ключевые термины из оригинального чанка
            chunk_terms = original_chunk.get("metadata", {}).get("key_terms", [])
            terms_covered.update(chunk_terms)
            
            formulas_pct = (formulas_covered / total_formulas * 100) if total_formulas else 100
            terms_pct = (len(terms_covered) / total_unique_terms * 100) if total_unique_terms else 100
            
            print(f"  Чанк {i}: +{chunk_data['formula_count']} формул, "
                  f"+{len(chunk_terms)} терминов | "
                  f"всего: {formulas_pct:.0f}% формул, {terms_pct:.0f}% терминов")
            
            # Проверяем достижение 80% по ОБОИМ показателям
            if formulas_covered >= target_formulas and len(terms_covered) >= target_terms:
                print(f"  ✅ Достигнуты оба порога 80% на чанке {i}")
                break
        
        # Если после цикла не достигли порога
        if formulas_covered < target_formulas or len(terms_covered) < target_terms:
            print(f"  ⚠ Порог 80% не достигнут даже со всеми чанками")
            print(f"     Формулы: {formulas_covered}/{target_formulas}")
            print(f"     Термины: {len(terms_covered)}/{target_terms}")
        
        # 6. Проверяем, что не меньше минимума
        if len(selected) < min_chunks:
            print(f"  ⚠ Добрано до минимума ({min_chunks} чанков)")
            for chunk_data in chunks_sorted[len(selected):min_chunks]:
                if len(selected) >= max_chunks:
                    break
                original_chunk = chunks[chunk_data["sequence"]]
                if original_chunk not in selected:
                    selected.append(original_chunk)
        
        # 7. Формируем информацию об отборе
        selection_info = {
            "total_chunks_in_file": len(chunks),
            "max_chunks_limit": max_chunks,
            "min_chunks_limit": min_chunks,
            "selected_count": len(selected),
            "target_coverage_pct": 80,
            "total_formulas": total_formulas,
            "total_unique_terms": total_unique_terms,
            "target_formulas": target_formulas,
            "target_terms": target_terms,
            "formulas_covered": formulas_covered,
            "formulas_coverage_pct": round(formulas_covered / total_formulas * 100, 1) if total_formulas else 100,
            "terms_covered": len(terms_covered),
            "terms_coverage_pct": round(len(terms_covered) / total_unique_terms * 100, 1) if total_unique_terms else 100,
            "threshold_reached": formulas_covered >= target_formulas and len(terms_covered) >= target_terms,
            "strategy": "80_percent_coverage",
            "available_context_tokens": max_details.get("available_for_chunks", "N/A"),
            "avg_chunk_tokens": stats["avg_chunk_tokens"]
        }
        
        print(f"\n✅ ОТОБРАНО ЧАНКОВ: {len(selected)}")
        print(f"  • Покрытие формул: {selection_info['formulas_coverage_pct']}%")
        print(f"  • Покрытие терминов: {selection_info['terms_coverage_pct']}%")
        print(f"  • Порог 80% достигнут: {'Да' if selection_info['threshold_reached'] else 'Нет'}")
        print(f"  • Доступно токенов под чанки: {selection_info['available_context_tokens']:,}")
        
        return selected, selection_info
    
    def extract_text_from_chunks(self, selected_chunks: List[Dict]) -> List[str]:
        """Извлекает текст из ОТОБРАННЫХ чанков"""
        texts = []
        for chunk in selected_chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        
        print(f"\n📝 Извлечено {len(texts)} текстовых блоков из отобранных чанков")
        
        if texts:
            print(f"   Пример первого блока:")
            print(f"   {texts[0][:200]}...")
        
        return texts
    
    def get_metadata(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает метаданные из pipeline"""
        return {
            'source_file': pipeline_data.get('source_file', 'unknown'),
            'process_id': pipeline_data.get('process_id', 'unknown'),
            'processed_at': pipeline_data.get('processed_at', 'unknown'),
            'statistics': pipeline_data.get('statistics', {}),
            'total_chunks': len(pipeline_data.get('chunks', []))
        }
    
    def create_prompt(self, texts: List[str], num_questions: int = 10, 
                      selection_info: Dict = None) -> str:
        """Создает промпт на основе отобранных текстов"""
        
        # Объединяем ВСЕ отобранные тексты
        context = "\n\n".join(texts)
        
        # Информация о покрытии для промпта
        coverage_note = ""
        if selection_info:
            coverage_note = f"""
ИНФОРМАЦИЯ О МАТЕРИАЛЕ:
- Отобрано {selection_info['selected_count']} фрагментов из {selection_info['total_chunks_in_file']}
- Покрытие формул: {selection_info['formulas_coverage_pct']}%
- Покрытие ключевых терминов: {selection_info['terms_coverage_pct']}%
- Стратегия отбора: {selection_info['strategy']}
"""
        
        prompt = f"""На основе предоставленного учебного материала создай тест из {num_questions} вопросов.
{coverage_note}
ИСХОДНЫЙ МАТЕРИАЛ:
{context}

ТРЕБОВАНИЯ К ТЕСТУ:
1. Все вопросы должны быть строго по содержанию материала
2. Каждый вопрос должен иметь 4 варианта ответа
3. Только один вариант ответа правильный
4. Вопросы должны проверять понимание ключевых концепций
5. Избегай тривиальных и очевидных вопросов
6. Включи вопросы разной сложности
7. Используй формулы и термины из материала

ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без пояснений):
{{
    "test_title": "Название теста по теме материала",
    "subject": "Определенная тема",
    "difficulty": "medium",
    "questions": [
        {{
            "id": 1,
            "question": "Текст вопроса",
            "options": ["Вариант А", "Вариант Б", "Вариант В", "Вариант Г"],
            "correct_answer": "Вариант А",
            "explanation": "Краткое пояснение правильного ответа"
        }}
    ]
}}

ВАЖНО: Верни ТОЛЬКО JSON, без дополнительного текста."""
        
        return prompt
    
    async def process_pipeline_json(self, json_path: str, num_questions: int = 10, 
                                    coverage_pct: int = 80) -> Dict[str, Any]:
        """
        Основной метод: загружает JSON, отбирает чанки по стратегии 80%,
        отправляет в GigaChat, возвращает тест
        
        Args:
            json_path: путь к JSON файлу
            num_questions: количество вопросов
            coverage_pct: процент покрытия (по умолчанию 80)
        """
        
        print("=" * 70)
        print(f"🚀 ОБРАБОТКА JSON С ОТБОРОМ ЧАНКОВ ({coverage_pct}% ПОКРЫТИЯ)")
        print("=" * 70)
        
        # 1. Загружаем JSON
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        # 2. Отбираем чанки по стратегии 80%
        selected_chunks, selection_info = self.select_chunks_80_percent(pipeline_data)
        
        if not selected_chunks:
            return {"error": "Не удалось отобрать чанки", "selection_info": selection_info}
        
        # 3. Извлекаем тексты из отобранных чанков
        texts = self.extract_text_from_chunks(selected_chunks)
        if not texts:
            return {"error": "Нет текстов для обработки"}
        
        # 4. Получаем метаданные
        metadata = self.get_metadata(pipeline_data)
        print(f"\n📋 Метаданные от pipeline:")
        print(f"  • Исходный файл: {metadata['source_file']}")
        print(f"  • Process ID: {metadata['process_id']}")
        print(f"  • Всего чанков в файле: {metadata['total_chunks']}")
        print(f"  • Отобрано чанков: {selection_info['selected_count']}")
        
        # 5. Создаем промпт с отобранными текстами
        prompt = self.create_prompt(texts, num_questions, selection_info)
        
        # Оценка токенов
        estimated_tokens = len(prompt) // 2  # грубая оценка для русского
        print(f"\n📤 ОТПРАВКА В GigaChat:")
        print(f"  • Вопросов: {num_questions}")
        print(f"  • Размер промпта: {len(prompt):,} символов (~{estimated_tokens:,} токенов)")
        print(f"  • Чанков в промпте: {len(texts)}")
        
        # 6. Отправляем в GigaChat
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f"✅ Ответ получен от GigaChat")
            
            # 7. Извлекаем JSON из ответа
            content = response['choices'][0]['message']['content']
            
            # Пытаемся найти JSON в ответе
            json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            # Очищаем от лишнего
            json_str = json_str.strip()
            if json_str.startswith('```'):
                json_str = json_str.split('```')[1]
                if json_str.startswith('json'):
                    json_str = json_str[4:]
            
            # Парсим JSON
            try:
                test_result = json.loads(json_str)
            except:
                # Если не получилось, пробуем найти JSON в тексте
                json_pattern = r'\{.*\}'
                match = re.search(json_pattern, json_str, re.DOTALL)
                if match:
                    test_result = json.loads(match.group())
                else:
                    test_result = {"raw_response": content, "questions": []}
            
            # 8. Добавляем метаданные
            test_result['pipeline_metadata'] = metadata
            test_result['selection_info'] = selection_info
            
            return test_result
            
        except Exception as e:
            print(f"❌ Ошибка при отправке в GigaChat: {e}")
            return {
                "error": str(e), 
                "pipeline_metadata": metadata,
                "selection_info": selection_info
            }
    
    def save_result(self, result: Dict[str, Any], output_path: str = None):
        """Сохраняет результат в JSON файл"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"test_result_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результат сохранен в: {output_path}")
        return output_path


async def main():
    """Основная функция"""
    
    # Путь к JSON файлу от pipeline 
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    # Проверяем существование файла
    if not Path(json_file).exists():
        print(f"❌ Ошибка, файл не найден: {json_file}")
        
        # Ищем в текущей папке
        current_dir = Path(__file__).parent
        possible_files = list(current_dir.glob("*.json"))
        if possible_files:
            print(f"\n🔍 Найденные JSON файлы в текущей папке:")
            for f in possible_files:
                print(f"  • {f}")
            
            # Берем первый
            json_file = str(possible_files[0])
            print(f"\n📁 Использую: {json_file}")
        else:
            return
    
    # Создаем процессор
    processor = PipelineJSONProcessor()
    
    # Обрабатываем JSON с отбором 80% чанков
    result = await processor.process_pipeline_json(
        json_path=json_file,
        num_questions=10,    # Количество вопросов
        coverage_pct=80      # Процент покрытия материала
    )
    
    # Сохраняем результат
    if 'error' not in result:
        output_file = processor.save_result(result)
        
        # Показываем статистику
        print("\n" + "=" * 70)
        print("📊 РЕЗУЛЬТАТ ГЕНЕРАЦИИ ТЕСТА")
        print("=" * 70)
        print(f"Название: {result.get('test_title', 'Не указано')}")
        print(f"Тема: {result.get('subject', 'Не указана')}")
        print(f"Сложность: {result.get('difficulty', 'Не указана')}")
        print(f"Вопросов: {len(result.get('questions', []))}")
        
        # Информация об отборе чанков
        selection_info = result.get('selection_info', {})
        if selection_info:
            print(f"\n📈 СТАТИСТИКА ОТБОРА ЧАНКОВ:")
            print(f"  • Отобрано: {selection_info['selected_count']} из {selection_info['total_chunks_in_file']}")
            print(f"  • Покрытие формул: {selection_info['formulas_coverage_pct']}%")
            print(f"  • Покрытие терминов: {selection_info['terms_coverage_pct']}%")
            print(f"  • Порог 80% достигнут: {'✅ Да' if selection_info['threshold_reached'] else '⚠️ Нет'}")
        
        if result.get('questions'):
            print(f"\n📝 ПРИМЕР ПЕРВОГО ВОПРОСА:")
            q = result['questions'][0]
            print(f"  Вопрос: {q.get('question', '')}")
            print("  Варианты:")
            for i, opt in enumerate(q.get('options', []), 1):
                print(f"    {i}. {opt}")
            print(f"  ✅ Правильный ответ: {q.get('correct_answer', '')}")
            print(f"  💡 Пояснение: {q.get('explanation', '')}")
    else:
        print(f"\n❌ Ошибка: {result['error']}")
        if 'selection_info' in result:
            print(f"   Статистика отбора: {result['selection_info']}")


if __name__ == "__main__":
    asyncio.run(main())
