"""
Обработка JSON файла от pipeline через GigaChat B2B клиент
с автоматическим отбором чанков по стратегии 80% покрытия
и ТОЧНЫМ подсчётом токенов через GigaChat API
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
    
    def count_tokens_accurate(self, texts: List[str]) -> int:
        """
        Точный подсчёт токенов через GigaChat API
        """
        if not texts:
            return 0
        
        try:
            # Используем синхронный метод, т.к. он быстрый
            result = self.client.tokens_count(
                input_=texts,
                model="GigaChat-Pro"
            )
            total_tokens = sum(result) if isinstance(result, list) else result
            return total_tokens
        except Exception as e:
            print(f"  ⚠ Ошибка точного подсчёта токенов: {e}")
            # Fallback: грубая оценка 3.5 символа = 1 токен
            total_chars = sum(len(text) for text in texts)
            return total_chars // 3.5
    
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
        Отбирает чанки по стратегии 80% покрытия с ТОЧНЫМ контролем токенов
        """
        chunks = pipeline_data.get('chunks', [])
        
        if not chunks:
            return [], {"error": "Нет чанков для отбора"}
        
        print(f"\n📊 АНАЛИЗ ЧАНКОВ:")
        print(f"  • Всего чанков в файле: {len(chunks)}")
        
        # 1. Считаем ТОЧНОЕ количество токенов для каждого чанка
        print(f"  • Подсчёт точного количества токенов...")
        
        chunk_texts = []
        for chunk in chunks:
            text = chunk.get('processed_text', '')
            chunk_texts.append(text)
        
        # Считаем токены через GigaChat API
        try:
            token_counts = self.client.tokens_count(
                input_=chunk_texts,
                model="GigaChat-Pro"
            )
            print(f"  ✅ Точный подсчёт токенов выполнен")
        except Exception as e:
            print(f"  ⚠ Не удалось точно посчитать токены: {e}")
            # Fallback: 3.5 символа на токен
            token_counts = [len(text) // 3.5 for text in chunk_texts]
            print(f"  • Использую приблизительный подсчёт (3.5 символов/токен)")
        
        # 2. Обновляем статистику с реальными токенами
        for i, chunk in enumerate(chunks):
            chunk['real_tokens'] = int(token_counts[i]) if isinstance(token_counts, list) else int(token_counts)
        
        total_tokens = sum(chunk['real_tokens'] for chunk in chunks)
        avg_tokens = total_tokens // len(chunks) if chunks else 0
        
        print(f"  • Общий объём: {total_tokens:,} токенов")
        print(f"  • Средний размер чанка: {avg_tokens} токенов")
        
        # 3. Считаем доступное место
        # GigaChat Pro: 130048 токенов контекста
        MAX_CONTEXT = 130048
        RESPONSE_RESERVE = 4000  # резерв под ответ
        PROMPT_OVERHEAD = 5000   # системный промпт + инструкции + JSON формат
        
        available_tokens = MAX_CONTEXT - RESPONSE_RESERVE - PROMPT_OVERHEAD
        max_chunks_by_tokens = max(1, available_tokens // avg_tokens) if avg_tokens > 0 else len(chunks)
        
        print(f"\n📐 РАСЧЁТ ЛИМИТОВ:")
        print(f"  • Контекст GigaChat: {MAX_CONTEXT:,} токенов")
        print(f"  • Резерв на ответ: {RESPONSE_RESERVE:,} токенов")
        print(f"  • Накладные расходы: {PROMPT_OVERHEAD:,} токенов")
        print(f"  • Доступно для чанков: {available_tokens:,} токенов")
        print(f"  • Максимум чанков по токенам: {max_chunks_by_tokens}")
        
        # 4. Определяем 80% от максимума
        target_chunks_80pct = int(max_chunks_by_tokens * 0.8)
        min_chunks = max(2, int(max_chunks_by_tokens * 0.1))  # минимум 10% или 2 чанка
        
        print(f"\n🎯 СТРАТЕГИЯ 80%:")
        print(f"  • 100% вмещается: {max_chunks_by_tokens} чанков")
        print(f"  • Цель (80%): {target_chunks_80pct} чанков")
        print(f"  • Минимум: {min_chunks} чанков")
        
        # 5. Анализируем чанки и сортируем по информативности
        stats = analyze_chunks_detailed(chunks)
        
        # 6. Сортируем по информативности (формулы + термины)
        chunks_with_scores = []
        for i, chunk in enumerate(chunks):
            meta = chunk.get("metadata", {})
            score = (
                meta.get("formula_count", 0) * 3.0 +
                len(meta.get("key_terms", [])) * 2.0 +
                meta.get("word_count", 0) * 0.3
            )
            chunks_with_scores.append({
                "chunk": chunk,
                "score": score,
                "tokens": chunk['real_tokens'],
                "formula_count": meta.get("formula_count", 0),
                "key_terms": meta.get("key_terms", []),
                "index": i
            })
        
        # Сортируем по важности
        chunks_with_scores.sort(key=lambda x: x["score"], reverse=True)
        
        # 7. Отбираем чанки с контролем токенов
        selected = []
        selected_tokens = 0
        formulas_covered = 0
        terms_covered = set()
        
        # Собираем все формулы и термины для статистики
        total_formulas = sum(c["formula_count"] for c in chunks_with_scores)
        all_terms = set()
        for c in chunks_with_scores:
            all_terms.update(c["key_terms"])
        total_unique_terms = len(all_terms)
        
        print(f"\n🔄 ОТБОР ЧАНКОВ:")
        print(f"  Цель: {target_chunks_80pct} чанков (80% от максимума)")
        
        for i, item in enumerate(chunks_with_scores, 1):
            # Проверяем лимиты
            if len(selected) >= target_chunks_80pct:
                print(f"  ✅ Достигнута цель: {target_chunks_80pct} чанков")
                break
            
            if selected_tokens + item["tokens"] > available_tokens:
                print(f"  ⚠ Достигнут лимит токенов")
                break
            
            selected.append(item["chunk"])
            selected_tokens += item["tokens"]
            formulas_covered += item["formula_count"]
            terms_covered.update(item["key_terms"])
        
        # 8. Проверяем минимум
        if len(selected) < min_chunks:
            print(f"  ⚠ Добираем до минимума ({min_chunks} чанков)")
            for item in chunks_with_scores[len(selected):]:
                if len(selected) >= min_chunks:
                    break
                if selected_tokens + item["tokens"] <= available_tokens:
                    selected.append(item["chunk"])
                    selected_tokens += item["tokens"]
        
        # 9. Статистика покрытия
        formulas_pct = (formulas_covered / total_formulas * 100) if total_formulas else 100
        terms_pct = (len(terms_covered) / total_unique_terms * 100) if total_unique_terms else 100
        
        selection_info = {
            "total_chunks_in_file": len(chunks),
            "max_chunks_by_tokens": max_chunks_by_tokens,
            "target_chunks_80pct": target_chunks_80pct,
            "selected_count": len(selected),
            "selected_tokens": selected_tokens,
            "available_tokens": available_tokens,
            "total_formulas": total_formulas,
            "total_unique_terms": total_unique_terms,
            "formulas_covered": formulas_covered,
            "formulas_coverage_pct": round(formulas_pct, 1),
            "terms_covered": len(terms_covered),
            "terms_coverage_pct": round(terms_pct, 1),
            "avg_chunk_tokens": avg_tokens,
            "strategy": "80_percent_with_accurate_tokens"
        }
        
        print(f"\n✅ РЕЗУЛЬТАТ ОТБОРА:")
        print(f"  • Отобрано: {len(selected)} из {target_chunks_80pct} целевых")
        print(f"  • Токенов использовано: {selected_tokens:,} из {available_tokens:,}")
        print(f"  • Покрытие формул: {formulas_pct:.1f}%")
        print(f"  • Покрытие терминов: {terms_pct:.1f}%")
        
        return selected, selection_info
    
    def extract_text_from_chunks(self, selected_chunks: List[Dict]) -> List[str]:
        """Извлекает текст из ОТОБРАННЫХ чанков"""
        texts = []
        for chunk in selected_chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        
        print(f"\n📝 Извлечено {len(texts)} текстовых блоков")
        
        if texts:
            preview = texts[0][:150]
            print(f"   Пример: {preview}...")
        
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
        
        context = "\n\n".join(texts)
        
        # Информация о покрытии
        coverage_note = ""
        if selection_info:
            coverage_note = f"""
ИНФОРМАЦИЯ О МАТЕРИАЛЕ:
- Отобрано {selection_info['selected_count']} фрагментов из {selection_info['total_chunks_in_file']}
- Покрытие формул: {selection_info['formulas_coverage_pct']}%
- Покрытие ключевых терминов: {selection_info['terms_coverage_pct']}%
"""
        
        prompt = f"""На основе предоставленного учебного материала создай тест из {num_questions} вопросов.
{coverage_note}
ИСХОДНЫЙ МАТЕРИАЛ:
{context}

ТРЕБОВАНИЯ К ТЕСТУ:
1. Все вопросы строго по содержанию материала
2. Каждый вопрос имеет 4 варианта ответа
3. Только один вариант правильный
4. Вопросы проверяют понимание ключевых концепций
5. Разная сложность вопросов
6. Используй формулы и термины из материала

ФОРМАТ ОТВЕТА (ТОЛЬКО JSON):
{{
    "test_title": "Название теста",
    "subject": "Тема",
    "difficulty": "medium",
    "questions": [
        {{
            "id": 1,
            "question": "Текст вопроса",
            "options": ["А", "Б", "В", "Г"],
            "correct_answer": "А",
            "explanation": "Пояснение"
        }}
    ]
}}

ВАЖНО: Верни ТОЛЬКО JSON!"""
        
        return prompt
    
    async def process_pipeline_json(self, json_path: str, num_questions: int = 10) -> Dict[str, Any]:
        """
        Основной метод обработки
        """
        print("=" * 70)
        print(f"🚀 ОБРАБОТКА JSON С ТОЧНЫМ ПОДСЧЁТОМ ТОКЕНОВ (80% СТРАТЕГИЯ)")
        print("=" * 70)
        
        # 1. Загружаем JSON
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        # 2. Отбираем чанки
        selected_chunks, selection_info = self.select_chunks_80_percent(pipeline_data)
        
        if not selected_chunks:
            return {"error": "Не удалось отобрать чанки", "selection_info": selection_info}
        
        # 3. Извлекаем тексты
        texts = self.extract_text_from_chunks(selected_chunks)
        if not texts:
            return {"error": "Нет текстов для обработки"}
        
        # 4. Метаданные
        metadata = self.get_metadata(pipeline_data)
        print(f"\n📋 Метаданные:")
        print(f"  • Файл: {metadata['source_file']}")
        print(f"  • Всего чанков: {metadata['total_chunks']}")
        print(f"  • Отобрано: {selection_info['selected_count']}")
        
        # 5. Создаем промпт
        prompt = self.create_prompt(texts, num_questions, selection_info)
        
        # 6. Проверяем итоговый размер
        final_tokens = self.count_tokens_accurate([prompt])
        print(f"\n📤 ФИНАЛЬНАЯ ПРОВЕРКА:")
        print(f"  • Размер промпта: {len(prompt):,} символов")
        print(f"  • Токенов (точно): {final_tokens:,}")
        print(f"  • Лимит GigaChat: 130,048")
        
        if final_tokens > 120000:
            print(f"  ⚠ Промпт всё ещё большой! Уменьшаем...")
            # Экстренно обрезаем тексты
            while final_tokens > 120000 and len(texts) > 2:
                texts = texts[:-1]
                prompt = self.create_prompt(texts, num_questions, selection_info)
                final_tokens = self.count_tokens_accurate([prompt])
                print(f"    Уменьшено до {len(texts)} текстов, {final_tokens:,} токенов")
        
        # 7. Отправляем в GigaChat
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f"✅ Ответ получен")
            
            # 8. Извлекаем JSON
            content = response['choices'][0]['message']['content']
            
            # Пытаемся распарсить JSON
            json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            json_str = json_str.strip()
            if json_str.startswith('```'):
                json_str = json_str.split('```')[1]
                if json_str.startswith('json'):
                    json_str = json_str[4:]
            
            try:
                test_result = json.loads(json_str)
            except:
                json_pattern = r'\{.*\}'
                match = re.search(json_pattern, json_str, re.DOTALL)
                if match:
                    test_result = json.loads(match.group())
                else:
                    test_result = {"raw_response": content, "questions": []}
            
            # 9. Добавляем метаданные
            test_result['pipeline_metadata'] = metadata
            test_result['selection_info'] = selection_info
            test_result['token_stats'] = {
                'final_prompt_tokens': final_tokens,
                'texts_used': len(texts),
                'prompt_chars': len(prompt)
            }
            
            return test_result
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return {
                "error": str(e), 
                "pipeline_metadata": metadata,
                "selection_info": selection_info
            }
    
    def save_result(self, result: Dict[str, Any], output_path: str = None):
        """Сохраняет результат"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"test_result_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Сохранено: {output_path}")
        return output_path


async def main():
    """Основная функция"""
    
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    if not Path(json_file).exists():
        print(f"❌ Файл не найден: {json_file}")
        return
    
    processor = PipelineJSONProcessor()
    
    result = await processor.process_pipeline_json(
        json_path=json_file,
        num_questions=10
    )
    
    if 'error' not in result:
        output_file = processor.save_result(result)
        
        print("\n" + "=" * 70)
        print("📊 РЕЗУЛЬТАТ")
        print("=" * 70)
        print(f"Название: {result.get('test_title', 'N/A')}")
        print(f"Тема: {result.get('subject', 'N/A')}")
        print(f"Вопросов: {len(result.get('questions', []))}")
        
        if result.get('questions'):
            q = result['questions'][0]
            print(f"\n📝 Пример вопроса:")
            print(f"  {q.get('question', '')}")
            print(f"  Варианты: {q.get('options', [])}")
            print(f"  Ответ: {q.get('correct_answer', '')}")
    else:
        print(f"\n❌ Ошибка: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
