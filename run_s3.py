"""
Обработка JSON файла от pipeline через GigaChat B2B клиент
с отбором чанков по стратегии "Топ по информативности"
и контролем заполнения контекстного окна.
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

from chunk_range_calculator import (
    estimate_tokens_gigachat,
    MODEL_CONFIG,
    TOTAL_PROMPT_OVERHEAD
)


class PipelineJSONProcessor:
    """Обработчик JSON файлов от pipeline с отправкой в GigaChat"""
    
    # Критерии отклонения некачественных чанков
    REJECT_CRITERIA = {
        "min_word_count": 10,           # Минимум слов
        "min_key_terms": 1,             # Минимум ключевых терминов
        "max_placeholder_ratio": 0.7,   # Максимум % формульных плейсхолдеров
        "min_clean_text_chars": 20,     # Минимум осмысленного текста (без формул)
        "min_lexical_diversity": 0.0,   # Можно ужесточить до 0.2
    }
    
    # Веса для расчета информативности
    SCORE_WEIGHTS = {
        "formula_count": 3.0,           # Каждая формула
        "key_terms_count": 2.0,         # Каждый ключевой термин
        "word_count_optimal": 2.0,      # Оптимальный размер (20-300 слов)
        "word_count_medium": 1.0,       # Приемлемый размер (10-500 слов)
        "lexical_diversity_high": 1.5,  # Лексическое разнообразие > 0.4
        "lexical_diversity_medium": 0.7,# Лексическое разнообразие > 0.3
        "has_topic": 2.0,               # Определена тема
        "has_definitions": 2.5,         # Содержит определения (если поле есть)
        "has_examples": 2.0,            # Содержит примеры (если поле есть)
        "sentence_count_optimal": 1.0,  # Оптимальное количество предложений (3-15)
        "topic_relevance_high": 3.0,    # Релевантность темы > 0.5 (если поле есть)
        "section_not_intro_conclusion": 1.5,  # Не введение/заключение
    }
    
    def __init__(self):
        self.client = GigaChatB2BClient()
        print(f" Инициализирован B2B клиент")
    
    def count_tokens_via_api(self, texts: List[str]) -> List[int]:
        """Точный подсчёт токенов через GigaChat API"""
        try:
            url = f"{self.client.base_url}/tokens/count"
            payload = {"model": "GigaChat-Pro", "input": texts}
            
            response = requests.post(
                url, headers=self.client.headers,
                json=payload, verify=False
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list):
                    print(f" Точный подсчёт через API выполнен")
                    return [int(r) for r in result]
            return None
        except Exception as e:
            print(f" ошибка : {e}")
            return None
    
    def load_pipeline_json(self, json_path: str) -> Dict[str, Any]:
        """Загружает JSON файл от pipeline"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f" Загружен JSON: {json_path}")
            return data
        except Exception as e:
            print(f" Ошибка загрузки JSON: {e}")
            return {}
    
    def _calculate_placeholder_ratio(self, text: str) -> float:
        """Вычисляет долю формульных плейсхолдеров в тексте"""
        if not text:
            return 0.0
        formulas = re.findall(r'\[\[FORMULA_[^\]]+\]\]', text)
        formula_chars = sum(len(f) for f in formulas)
        return formula_chars / len(text) if len(text) > 0 else 0.0
    
    def _check_chunk_quality(self, chunk: Dict) -> Tuple[bool, str]:
        """
        Проверяет обязательные критерии качества чанка.
        Возвращает (passed, reason).
        """
        text = chunk.get('processed_text', '')
        metadata = chunk.get('metadata', {})
        
        # 1. Минимальное количество слов
        word_count = metadata.get('word_count', 0)
        if word_count < self.REJECT_CRITERIA['min_word_count']:
            return False, f"word_count={word_count}"
        
        # 2. Наличие ключевых терминов
        key_terms = metadata.get('key_terms', [])
        if len(key_terms) < self.REJECT_CRITERIA['min_key_terms']:
            return False, "key_terms пуст"
        
        # 3. Не слишком много плейсхолдеров
        placeholder_ratio = self._calculate_placeholder_ratio(text)
        if placeholder_ratio > self.REJECT_CRITERIA['max_placeholder_ratio']:
            return False, f"placeholder_ratio={placeholder_ratio:.2f}"
        
        # 4. Минимум осмысленного текста (без формул)
        clean_text = re.sub(r'\[\[FORMULA_[^\]]+\]\]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if len(clean_text) < self.REJECT_CRITERIA['min_clean_text_chars']:
            return False, f"clean_text={len(clean_text)} chars"
        
        return True, "OK"
    
    def _calculate_informativeness_score(self, chunk: Dict) -> float:
        """
        Вычисляет score информативности чанка.
        Учитывает формулы, термины, размер, разнообразие, тему и др.
        """
        metadata = chunk.get('metadata', {})
        score = 0.0
        
        # 1. Формулы
        formula_count = metadata.get('formula_count', 0)
        score += formula_count * self.SCORE_WEIGHTS['formula_count']
        
        # 2. Ключевые термины
        key_terms = metadata.get('key_terms', [])
        score += len(key_terms) * self.SCORE_WEIGHTS['key_terms_count']
        
        # 3. Оптимальный размер
        word_count = metadata.get('word_count', 0)
        if 20 <= word_count <= 300:
            score += self.SCORE_WEIGHTS['word_count_optimal']
        elif 10 <= word_count <= 500:
            score += self.SCORE_WEIGHTS['word_count_medium']
        
        # 4. Лексическое разнообразие
        lexical_diversity = metadata.get('lexical_diversity', 0)
        if lexical_diversity > 0.4:
            score += self.SCORE_WEIGHTS['lexical_diversity_high']
        elif lexical_diversity > 0.3:
            score += self.SCORE_WEIGHTS['lexical_diversity_medium']
        
        # 5. Определена тема
        main_topic = metadata.get('main_topic', '')
        if main_topic and main_topic not in ['неизвестно', 'unknown', '']:
            score += self.SCORE_WEIGHTS['has_topic']
        
        # 6. Определения (если поле есть)
        if metadata.get('has_definitions', False):
            score += self.SCORE_WEIGHTS['has_definitions']
        
        # 7. Примеры (если поле есть)
        if metadata.get('has_examples', False):
            score += self.SCORE_WEIGHTS['has_examples']
        
        # 8. Оптимальное количество предложений
        sentence_count = metadata.get('sentence_count', 0)
        if 3 <= sentence_count <= 15:
            score += self.SCORE_WEIGHTS['sentence_count_optimal']
        
        # 9. Релевантность темы (если поле есть)
        topic_relevance = metadata.get('topic_relevance', 0)
        if topic_relevance > 0.5:
            score += self.SCORE_WEIGHTS['topic_relevance_high']
        
        # 10. Тип секции (не введение/заключение)
        section_type = metadata.get('section_type', '')
        if section_type and section_type not in ['введение', 'заключение', 
                                                   'introduction', 'conclusion']:
            score += self.SCORE_WEIGHTS['section_not_intro_conclusion']
        
        return score
    
    def select_chunks_top_informativeness(self, 
                                          pipeline_data: Dict[str, Any],
                                          coverage_pct: int = 80) -> Tuple[List[Dict], Dict]:
        """
        Отбирает чанки по принципу "Топ по информативности"
        с контролем заполнения контекстного окна.
        
        Алгоритм:
        1. Фильтрует некачественные чанки
        2. Считает score информативности для каждого
        3. Сортирует по убыванию score
        4. Отбирает лучшие, пока не заполнит целевой % контекста
        """
        chunks = pipeline_data.get('chunks', [])
        
        if not chunks:
            return [], {"error": "Нет чанков для отбора"}
        
        print(f" Отбор чанок: информативность")
        # === ШАГ 1: Фильтрация некачественных чанков ===
        print(f"\n ШАГ 1: Фильтрация качества.")
        print(f"  Всего чанков: {len(chunks)}")
        
        passed_chunks = []
        rejected_stats = {}
        
        for i, chunk in enumerate(chunks):
            passed, reason = self._check_chunk_quality(chunk)
            if passed:
                passed_chunks.append({'chunk': chunk, 'index': i})
            else:
                rejected_stats[reason] = rejected_stats.get(reason, 0) + 1
        
        print(f"  Прошло фильтрацию: {len(passed_chunks)} чанков")
        print(f"  Отклонено: {len(chunks) - len(passed_chunks)} чанков")
        
        if rejected_stats:
            print(f"  Причины отклонения:")
            for reason, count in sorted(rejected_stats.items(), 
                                        key=lambda x: -x[1]):
                print(f"    - {reason}: {count}")
        
        if not passed_chunks:
            print(f"  Все чанки отклонены! Использую все без фильтрации.")
            passed_chunks = [{'chunk': c, 'index': i} 
                           for i, c in enumerate(chunks)]
        
        # === ШАГ 2: Подсчёт токенов и score ===
        print(f"\n ШАГ 2: Оценка информативности и токенов.")
        
        for item in passed_chunks:
            text = item['chunk'].get('processed_text', '')
            item['tokens'] = estimate_tokens_gigachat(text)
            item['score'] = self._calculate_informativeness_score(item['chunk'])
            item['formula_count'] = item['chunk'].get('metadata', {}).get('formula_count', 0)
            item['key_terms'] = item['chunk'].get('metadata', {}).get('key_terms', [])
        
        # Сортируем по убыванию score
        passed_chunks.sort(key=lambda x: x['score'], reverse=True)
        
        # Статистика scores
        scores = [item['score'] for item in passed_chunks]
        if scores:
            print(f"  • Score: мин={min(scores):.1f}, макс={max(scores):.1f}, "
                  f"сред={sum(scores)/len(scores):.1f}")
        
        # Топ-5 для информации
        print(f"  Топ-5 чанков:")
        for i, item in enumerate(passed_chunks[:5], 1):
            meta = item['chunk'].get('metadata', {})
            print(f"    {i}. Score={item['score']:.1f} | "
                  f"Слов={meta.get('word_count', 0)} | "
                  f"Формул={meta.get('formula_count', 0)} | "
                  f"Терминов={len(meta.get('key_terms', []))} | "
                  f"Токенов={item['tokens']}")
        
        # === ШАГ 3: Расчёт лимитов ===
        print(f"\n ШАГ 3: Расчёт лимита токенов.")
        
        MAX_CONTEXT = MODEL_CONFIG["context_window"]
        RESPONSE_RESERVE = MODEL_CONFIG["max_output_tokens"]
        PROMPT_OVERHEAD = TOTAL_PROMPT_OVERHEAD + 2_000
        SAFETY_MARGIN = 0.90
        
        available_tokens = int(
            (MAX_CONTEXT - RESPONSE_RESERVE - PROMPT_OVERHEAD) * SAFETY_MARGIN
        )
        
        target_tokens = int(available_tokens * coverage_pct / 100)
        
        print(f"  Доступно токенов: {available_tokens:,}")
        print(f"  Целевое заполнение: {coverage_pct}%")
        print(f"  Целевой объём: {target_tokens:,} токенов")
        
        # === ШАГ 4: Отбор с контролем токенов ===
        print(f"\n ШАГ 4: Отбор лучших чанков...")
        
        selected = []
        selected_tokens = 0
        formulas_covered = 0
        terms_covered = set()
        
        total_formulas = sum(item['formula_count'] for item in passed_chunks)
        all_terms = set()
        for item in passed_chunks:
            all_terms.update(item['key_terms'])
        
        for i, item in enumerate(passed_chunks, 1):
            if selected_tokens + item['tokens'] > target_tokens:
                # Проверяем, можно ли добавить частично
                remaining = target_tokens - selected_tokens
                if remaining > item['tokens'] * 0.5:
                    selected.append(item['chunk'])
                    selected_tokens += item['tokens']
                    formulas_covered += item['formula_count']
                    terms_covered.update(item['key_terms'])
                break
            
            selected.append(item['chunk'])
            selected_tokens += item['tokens']
            formulas_covered += item['formula_count']
            terms_covered.update(item['key_terms'])
        
        # === ШАГ 5: Статистика ===
        formulas_pct = (formulas_covered / total_formulas * 100) if total_formulas else 100
        terms_pct = (len(terms_covered) / len(all_terms) * 100) if all_terms else 100
        
        selection_info = {
            "total_chunks_in_file": len(chunks),
            "passed_filter": len(passed_chunks),
            "rejected": len(chunks) - len(passed_chunks),
            "selected_count": len(selected),
            "selected_tokens": selected_tokens,
            "target_tokens": target_tokens,
            "available_tokens": available_tokens,
            "token_usage_pct": round(selected_tokens / available_tokens * 100, 1),
            "total_formulas": total_formulas,
            "formulas_covered": formulas_covered,
            "formulas_coverage_pct": round(formulas_pct, 1),
            "total_unique_terms": len(all_terms),
            "terms_covered": len(terms_covered),
            "terms_coverage_pct": round(terms_pct, 1),
            "avg_score": (sum(item['score'] for item in passed_chunks[:len(selected)]) 
                         / len(selected)) if selected else 0,
            "strategy": "top_informativeness"
        }
        
        print(f" Результаты ")
        print(f"  Отобрано: {len(selected)} чанков")
        print(f"  Средний score: {selection_info['avg_score']:.1f}")
        print(f"  Токенов: {selected_tokens:,} из {target_tokens:,} "
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
            #print(f"   Пример: {preview}...")
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
- Отобрано {selection_info['selected_count']} наиболее информативных фрагментов
- Средний score: {selection_info.get('avg_score', 0):.1f}
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
                                    num_questions: int = 10,
                                    coverage_pct: int = 80) -> Dict[str, Any]:
        """Основной метод обработки"""
        
        
        print(f"Обработка Json: ТОП ПО ИНФОРМАТИВНОСТИ ({coverage_pct}%)")
        
        
        # 1. Загружаем JSON
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        # 2. Отбираем чанки по информативности
        selected_chunks, selection_info = self.select_chunks_top_informativeness(
            pipeline_data, coverage_pct
        )
        
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
        print(f"  Файл: {metadata['source_file']}")
        print(f"  Чанков в файле: {metadata['total_chunks']}")
        print(f"  Отобрано: {len(selected_chunks)}")
        
        # 5. Создаем промпт
        prompt = self.create_prompt(texts, num_questions, selection_info)
        
        # 6. Финальная проверка размера
        print(f"\n Финальная проверка:")
        print(f"  Размер промпта: {len(prompt):,} символов")
        
        final_tokens = estimate_tokens_gigachat(prompt)
        print(f"  Токенов (оценка): {final_tokens:,}")
        print(f"  Лимит GigaChat: {MODEL_CONFIG['context_window']:,}")
        
        # 7. Отправляем в GigaChat
        print(f"\n Отправка в GigaChat.")
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f"Ответ получен")
            content = response['choices'][0]['message']['content']
            
            # Очистка LaTeX
            def clean_json_for_parsing(json_str: str) -> str:
                cleaned = json_str.replace('\\\\', '<<<DBL>>>')
                cleaned = cleaned.replace('\\"', '<<<QUOTE>>>')
                cleaned = cleaned.replace('\\n', '<<<NL>>>')
                cleaned = cleaned.replace('\\t', '<<<TAB>>>')
                cleaned = cleaned.replace('\\', '\\\\')
                cleaned = cleaned.replace('<<<DBL>>>', '\\\\\\\\')
                cleaned = cleaned.replace('<<<QUOTE>>>', '\\"')
                cleaned = cleaned.replace('<<<NL>>>', '\\n')
                cleaned = cleaned.replace('<<<TAB>>>', '\\t')
                return cleaned
            
            # Извлечение JSON
            json_match = re.search(r'```json\s*\n(.*?)\n\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                start = content.find('{')
                end = content.rfind('}')
                json_str = content[start:end+1] if start != -1 and end != -1 else content
            
            json_str = json_str.strip()
            if json_str.startswith('```'):
                parts = json_str.split('```')
                json_str = parts[1] if len(parts) > 1 else json_str
                if json_str.startswith('json'):
                    json_str = json_str[4:]
            json_str = json_str.strip()
            
            # Парсинг JSON
            test_result = None
            try:
                test_result = json.loads(json_str)
                print(" JSON успешно распарсен")
            except json.JSONDecodeError as e:
                print(f"  Ошибка JSON: {e}")
                try:
                    cleaned = clean_json_for_parsing(json_str)
                    test_result = json.loads(cleaned)
                    print(" JSON распарсен после очистки LaTeX")
                except:
                    test_result = {"raw_response": content, "questions": []}
            
            # Добавляем метаданные
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
        
        if "raw_response" in result:
            raw_path = output_path.replace('.json', '_raw.txt')
            with open(raw_path, 'w', encoding='utf-8') as f:
                f.write(result["raw_response"])
            print(f"💾 Сырой ответ сохранён: {raw_path}")
        
        try:
            serializable_result = json.loads(
                json.dumps(result, ensure_ascii=False, default=str)
            )
        except:
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
        num_questions=10,
        coverage_pct=80
    )
    
    if 'error' not in result:
        output_file = processor.save_result(result)
    
        print(" Результат")
        
        selection_info = result.get('selection_info', {})
        if selection_info:
            print(f"\n СТАТИСТИКА ОТБОРА:")
            print(f"  Стратегия: {selection_info.get('strategy', 'N/A')}")
            print(f"  Отобрано: {selection_info['selected_count']} чанков")
            print(f"  Средний score: {selection_info.get('avg_score', 0):.1f}")
            print(f"  Покрытие формул: {selection_info['formulas_coverage_pct']}%")
            print(f"  Покрытие терминов: {selection_info['terms_coverage_pct']}%")
        
       


if __name__ == "__main__":
    asyncio.run(main())
