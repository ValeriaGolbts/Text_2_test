"""
Обработка JSON файла от pipeline через GigaChat B2B клиент
с автоматическим отбором чанков по стратегии 80% от максимально возможного.
Поддерживает точный подсчёт токенов через GigaChat API.
"""
import json
import asyncio
import sys
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from api_client_b2b import GigaChatB2BClient
from config import config

# Импортируем функции из улучшенного chunk_range_calculator
from chunk_range_calculator import (
    analyze_chunks_detailed,
    calculate_max_chunks,
    calculate_min_chunks,
    estimate_tokens_gigachat,
    MODEL_CONFIG,
    TOTAL_PROMPT_OVERHEAD
)


class PipelineJSONProcessor:
    """Обработчик JSON файлов от pipeline с отправкой в GigaChat"""
    
    def __init__(self):
        self.client = GigaChatB2BClient()
        print(f"Инициализирован B2B клиент")
    
    def count_tokens_via_api(self, texts: List[str]) -> List[int]:
        """
        Точный подсчёт токенов через официальный эндпоинт GigaChat API.
        POST /api/v1/tokens/count
        """
        """try:
            url = f"{self.client.base_url}/tokens/count"
            
            payload = {
                "model": "GigaChat-Pro",
                "input": texts
            }
            
            response = requests.post(
                url,
                headers=self.client.headers,
                json=payload,
                verify=False
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if isinstance(result, list):
                    print(f"Точный подсчёт через API выполнен")
                    return [int(r) for r in result]
                elif isinstance(result, dict):
                    # Разные форматы ответа
                    if "tokens" in result:
                        return [int(result["tokens"])]
                    elif "data" in result and isinstance(result["data"], list):
                        return [int(r) for r in result["data"]]
                    else:
                        print(f"Неизвестный формат ответа API")
                        return None
            else:
                print(f"API Error {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"  Ошибка при обращении к API: {e}")"""
            return None
    
    def load_pipeline_json(self, json_path: str) -> Dict[str, Any]:
        """Загружает JSON файл от pipeline"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"Загружен JSON: {json_path}")
            return data
        except Exception as e:
            print(f"Ошибка загрузки JSON: {e}")
            return {}
    
    def select_chunks_80_percent(self, pipeline_data: Dict[str, Any]) -> Tuple[List[Dict], Dict]:
        """
        Отбирает чанки по стратегии 80% от МАКСИМАЛЬНО ВОЗМОЖНОГО количества.
        
        Алгоритм:
        1. Считает токены точно (через API) или реалистично
        2. Определяет, сколько чанков МАКСИМАЛЬНО влезает в контекст
        3. Берёт 80% от этого максимума
        4. Отбирает самые информативные чанки
        """
        chunks = pipeline_data.get('chunks', [])
        
        if not chunks:
            return [], {"error": "Нет чанков для отбора"}
        
        
        print(f"Анализ чанков и расчет лимитов")
        print(f"Всего чанков: {len(chunks)}")
        
        # === ШАГ 1: Подсчёт токенов ===
        chunk_texts = [chunk.get('processed_text', '') for chunk in chunks]
        
        print(f"\n Подсчет токенов:")
        
        # Пробуем точный подсчёт через API
        #token_counts = self.count_tokens_via_api(chunk_texts)
        token_counts = None
        
        if token_counts is None or len(token_counts) != len(chunks):
            # Fallback: реалистичная оценка
            print(f" Использую реалистичную оценку токенов")
            token_counts = [estimate_tokens_gigachat(text) for text in chunk_texts]
            
            # Показываем сравнение со старой оценкой
            old_estimate = sum(len(t) // 3.5 for t in chunk_texts)
            new_estimate = sum(token_counts)
            print(f"Старая оценка (3.5 симв/ток): {old_estimate:,} токенов")
            print(f"Новая оценка (с формулами): {new_estimate:,} токенов")
            if old_estimate > 0:
                print(f"Разница: в {new_estimate/old_estimate:.1f} раз больше")
        
        total_tokens = sum(token_counts)
        avg_tokens = total_tokens // len(chunks) if chunks else 0
        
        print(f"Общий объём: {total_tokens:,} токенов")
        print(f"Средний чанк: {avg_tokens} токенов")
        print(f" Мин/Макс чанка: {min(token_counts)}/{max(token_counts)} токенов")
        
        # === ШАГ 2: Расчёт лимитов ===
        print(f"\n Расчет доступного места:")
        
        # Параметры GigaChat Pro
        MAX_CONTEXT = MODEL_CONFIG["context_window"]  # 130 048
        RESPONSE_RESERVE = MODEL_CONFIG["max_output_tokens"]  # 4 096
        PROMPT_OVERHEAD = TOTAL_PROMPT_OVERHEAD + 2_000  # 3 400 + запас 2 000
        SAFETY_MARGIN = 0.90
        
        available_tokens = int(
            (MAX_CONTEXT - RESPONSE_RESERVE - PROMPT_OVERHEAD) * SAFETY_MARGIN
        )
        
        print(f"  Контекст GigaChat Pro: {MAX_CONTEXT:,} токенов")
        print(f"  Резерв на ответ: {RESPONSE_RESERVE:,} токенов")
        print(f"  Накладные расходы: {PROMPT_OVERHEAD:,} токенов")
        print(f"  Запас безопасности: {SAFETY_MARGIN*100:.0f}%")
        print(f"  ДОСТУПНО ДЛЯ ЧАНКОВ: {available_tokens:,} токенов")
        
        # === ШАГ 3: Сколько чанков РЕАЛЬНО влезает ===
        print(f"\n СКОЛЬКО ЧАНКОВ ВЛЕЗАЕТ:")
        
        # Сортируем по токенам (для точного подсчёта)
        chunks_with_tokens = list(zip(chunks, token_counts))
        
        # Считаем, сколько влезает
        tokens_used = 0
        max_chunks_real = 0
        
        for chunk, tokens in chunks_with_tokens:
            if tokens_used + tokens > available_tokens:
                break
            tokens_used += tokens
            max_chunks_real += 1
        
        print(f" Максимально влезает: {max_chunks_real} чанков")
        print(f" Это {max_chunks_real/len(chunks)*100:.1f}% от всех чанков")
        
        if max_chunks_real < len(chunks):
            print(f" Не влезает: {len(chunks) - max_chunks_real} чанков")
        
        # === ШАГ 4: Стратегия 80% ===
        target_chunks = max(2, int(max_chunks_real * 0.6))
        
        print(f"\n Стратегия 80% от макимума:")
        print(f"  100% (максимально влезает): {max_chunks_real} чанков")
        print(f"  80% от максимума: {target_chunks} чанков")
        
        # === ШАГ 5: Сортировка по информативности ===
        chunks_scored = []
        for i, (chunk, tokens) in enumerate(zip(chunks, token_counts)):
            meta = chunk.get("metadata", {})
            score = (
                meta.get("formula_count", 0) * 3.0 +
                len(meta.get("key_terms", [])) * 2.0 +
                meta.get("word_count", 0) * 0.3
            )
            chunks_scored.append({
                "chunk": chunk,
                "tokens": tokens,
                "score": score,
                "formula_count": meta.get("formula_count", 0),
                "key_terms": meta.get("key_terms", []),
                "index": i
            })
        
        # Сортировка: сначала самые важные
        chunks_scored.sort(key=lambda x: x["score"], reverse=True)
        
        # === ШАГ 6: Отбор лучших чанков с контролем токенов ===
        selected = []
        selected_tokens = 0
        formulas_covered = 0
        terms_covered = set()
        
        # Статистика для всего документа
        total_formulas = sum(c["formula_count"] for c in chunks_scored)
        all_terms = set()
        for c in chunks_scored:
            all_terms.update(c["key_terms"])
        
        print(f"\n Отбор {target_chunks} лучших:")
        
        for i, item in enumerate(chunks_scored):
            if len(selected) >= target_chunks:
                break
            
            if selected_tokens + item["tokens"] > available_tokens:
                print(f" Достигнут лимит токенов на чанке {i+1}")
                break
            
            selected.append(item["chunk"])
            selected_tokens += item["tokens"]
            formulas_covered += item["formula_count"]
            terms_covered.update(item["key_terms"])
        
        # === ШАГ 7: Статистика ===
        formulas_pct = (formulas_covered / total_formulas * 100) if total_formulas else 100
        terms_pct = (len(terms_covered) / len(all_terms) * 100) if all_terms else 100
        
        selection_info = {
            "total_chunks_in_file": len(chunks),
            "total_tokens_all": total_tokens,
            "max_chunks_possible": max_chunks_real,
            "target_chunks_80pct": target_chunks,
            "selected_count": len(selected),
            "selected_tokens": selected_tokens,
            "available_tokens": available_tokens,
            "token_usage_pct": round(selected_tokens / available_tokens * 100, 1),
            "total_formulas": total_formulas,
            "total_unique_terms": len(all_terms),
            "formulas_covered": formulas_covered,
            "formulas_coverage_pct": round(formulas_pct, 1),
            "terms_covered": len(terms_covered),
            "terms_coverage_pct": round(terms_pct, 1),
            "strategy": "80_percent_of_max_possible"
        }
    
        print(f" Резльтат отбора")
        print(f"  Отобрано: {len(selected)} из {max_chunks_real} возможных")
        print(f"  Токенов: {selected_tokens:,} из {available_tokens:,} "
              f"({selection_info['token_usage_pct']}%)")
        print(f"  Покрытие формул: {formulas_pct:.1f}%")
        print(f"  Покрытие терминов: {terms_pct:.1f}%")
        
        return selected, selection_info
    
    def extract_text_from_chunks(self, selected_chunks: List[Dict]) -> List[str]:
        """Извлекает текст из отобранных чанков"""
        texts = []
        for chunk in selected_chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        
        print(f"\n Извлечено {len(texts)} текстовых блоков")
        
        if texts:
            preview = texts[0][:150].replace('\n', ' ')
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
        
        coverage_note = ""
        if selection_info:
            coverage_note = f"""
ИНФОРМАЦИЯ О МАТЕРИАЛЕ:
- Отобрано {selection_info['selected_count']} фрагментов (80% от максимума)
- Покрытие формул: {selection_info['formulas_coverage_pct']}%
- Покрытие ключевых терминов: {selection_info['terms_coverage_pct']}%
- Использовано токенов: {selection_info['selected_tokens']:,} из {selection_info['available_tokens']:,}
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
    
    async def process_pipeline_json(self, json_path: str, 
                                    num_questions: int = 10) -> Dict[str, Any]:
        """Основной метод обработки"""
        
        print("ОБРАБОТКА.")
        
        # 1. Загружаем JSON
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        # 2. Отбираем чанки (80% от максимума)
        selected_chunks, selection_info = self.select_chunks_80_percent(pipeline_data)
        
        if not selected_chunks:
            return {"error": "Не удалось отобрать чанки", 
                    "selection_info": selection_info}
        
        # 3. Извлекаем тексты
        texts = self.extract_text_from_chunks(selected_chunks)
        if not texts:
            return {"error": "Нет текстов для обработки"}
        
        # 4. Метаданные
        metadata = self.get_metadata(pipeline_data)
        print(f"\n Метаданные:")
        print(f" Файл: {metadata['source_file']}")
        print(f" Чанков в файле: {metadata['total_chunks']}")
        print(f" Отобрано: {len(selected_chunks)}")
        
        # 5. Создаем промпт
        prompt = self.create_prompt(texts, num_questions, selection_info)
        
        # 6. Финальная проверка размера
        print(f"\n Финальная проверка:")
        print(f"  Размер промпта: {len(prompt):,} символов")
        #token_counts = self.count_tokens_via_api(chunk_texts)
        # Пробуем точный подсчёт
        #final_tokens = self.count_tokens_via_api([prompt])
        #if final_tokens:
           # final_tokens = final_tokens[0]
          #  print(f"  Токенов (точно): {final_tokens:,}")
       # else:
        final_tokens = estimate_tokens_gigachat(prompt)
        print(f"  Токенов (оценка): {final_tokens:,}")
        
        print(f"  Лимит GigaChat: {MODEL_CONFIG['context_window']:,}")
        
        if final_tokens > MODEL_CONFIG['context_window'] * 0.95:
            print(f" Промпт всё ещё большой!")
            while final_tokens > MODEL_CONFIG['context_window'] * 0.95 and len(texts) > 2:
                texts = texts[:-1]
                prompt = self.create_prompt(texts, num_questions, selection_info)
                final_tokens = estimate_tokens_gigachat(prompt)
                print(f"    Уменьшено до {len(texts)} текстов, ~{final_tokens:,} токенов")
        
        # 7. Отправляем в GigaChat
        print(f"\n Отправка запроса в GigaChat")
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f"Ответ получен!")
            
            content = response['choices'][0]['message']['content']
            
            # Исправленная функция очистки LaTeX
            def clean_json_for_parsing(json_str: str) -> str:
                """Очищает JSON строку от проблемных LaTeX символов"""
                # Заменяем все одиночные бэкслеши на двойные
                # Но сохраняем уже правильные escape-последовательности (\n, \t, \", \\)
                cleaned = json_str.replace('\\\\', '<<<DOUBLE_BACKSLASH>>>')  # Сохраняем \\
                cleaned = cleaned.replace('\\"', '<<<ESCAPED_QUOTE>>>')       # Сохраняем \"
                cleaned = cleaned.replace('\\n', '<<<NEWLINE>>>')             # Сохраняем \n
                cleaned = cleaned.replace('\\t', '<<<TAB>>>')                 # Сохраняем \t
                cleaned = cleaned.replace('\\', '\\\\')                        # Экранируем все оставшиеся \
                cleaned = cleaned.replace('<<<DOUBLE_BACKSLASH>>>', '\\\\\\\\') # Возвращаем \\
                cleaned = cleaned.replace('<<<ESCAPED_QUOTE>>>', '\\"')       # Возвращаем \"
                cleaned = cleaned.replace('<<<NEWLINE>>>', '\\n')             # Возвращаем \n
                cleaned = cleaned.replace('<<<TAB>>>', '\\t')                 # Возвращаем \t
                return cleaned
            
            json_match = re.search(r'```json\s*\n(.*?)\n\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Ищем JSON без маркеров (от первой { до последней })
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    json_str = content[start:end+1]
                else:
                    json_str = content
            
            json_str = json_str.strip()
            if json_str.startswith('```'):
                parts = json_str.split('```')  # ← ИСПРАВЛЕНО: было parts, а не json_str
                json_str = parts[1] if len(parts) > 1 else json_str
                if json_str.startswith('json'):
                    json_str = json_str[4:]
            json_str = json_str.strip()
            
            # Парсим JSON с несколькими попытками
            test_result = None
                               
            try:
                test_result = json.loads(json_str)
                print(" JSON успешно распарсен")
            except json.JSONDecodeError as e:
                print(f" Ошибка JSON (попытка 1): {e}")
                
                try:
                    cleaned_json = clean_json_for_parsing(json_str)
                    test_result = json.loads(cleaned_json)
                    print(" JSON распарсен после очистки LaTeX")
                except json.JSONDecodeError as e2:
                    print(f" Ошибка JSON (попытка 2): {e2}")
                    
                    try:
                        json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
                        match = re.search(json_pattern, json_str, re.DOTALL)
                        if match:
                            found_json = match.group()
                            try:
                                test_result = json.loads(found_json)
                            except:
                                cleaned = clean_json_for_parsing(found_json)
                                test_result = json.loads(cleaned)
                            print(" JSON найден через регулярку")
                    except Exception as e3:
                        print(f" Ошибка JSON (попытка 3): {e3}")
                        
                        try:
                            no_latex = re.sub(r'\\[a-zA-Z]+', '', json_str)
                            test_result = json.loads(no_latex)
                            print(" JSON распарсен после удаления LaTeX")
                        except Exception as e4:
                            print(f" Все попытки парсинга не удались")
                            test_result = {
                                "raw_response": content,
                                "questions": [],
                                "parse_error": str(e4)
                            }
            
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
            print(f" Ошибка: {e}")
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
        
        # Если есть сырой ответ - сохраняем и его
        if "raw_response" in result:
            raw_path = output_path.replace('.json', '_raw.txt')
            with open(raw_path, 'w', encoding='utf-8') as f:
                f.write(result["raw_response"])
            print(f" Сырой ответ сохранён: {raw_path}")
        
        # Сохраняем JSON (конвертируем сложные объекты в строки)
        try:
            serializable_result = json.loads(
                json.dumps(result, ensure_ascii=False, default=str)
            )
        except:
            # Если не получается сериализовать - сохраняем как есть
            serializable_result = result
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_result, f, ensure_ascii=False, indent=2)
        
        print(f" Результат сохранён: {output_path}")
        return output_path
           

async def main():
    """Основная функция"""
    
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    if not Path(json_file).exists():
        print(f" Файл не найден: {json_file}")
        
        current_dir = Path(__file__).parent
        possible_files = list(current_dir.glob("*.json"))
        if possible_files:
            print(f"\n Найденные JSON файлы:")
            for f in possible_files:
                print(f"  • {f}")
            json_file = str(possible_files[0])
            print(f"\n Использую: {json_file}")
        else:
            return
    
    processor = PipelineJSONProcessor()
    
    result = await processor.process_pipeline_json(
        json_path=json_file,
        num_questions=10
    )
    
    if 'error' not in result:
        output_file = processor.save_result(result)
        
        print("РЕЗУЛЬТАТ")
                
        selection_info = result.get('selection_info', {})
        if selection_info:
            print(f"\n СТАТИСТИКА ОТБОРА:")
            print(f"  Отобрано: {selection_info['selected_count']} чанков")
            print(f"  Покрытие формул: {selection_info['formulas_coverage_pct']}%")
            print(f"  Покрытие терминов: {selection_info['terms_coverage_pct']}%")
            print(f"  Использовано токенов: {selection_info['selected_tokens']:,}")


if __name__ == "__main__":
    asyncio.run(main())
