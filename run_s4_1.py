"""
Обработка JSON файла от pipeline через GigaChat B2B клиент
с отбором чанков по стратегии "Ползучее накопление" (до 90% контекстного окна).
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
        "min_word_count": 10,
        "min_key_terms": 1,
        "max_placeholder_ratio": 0.7,
        "min_clean_text_chars": 20,
    }
    
    # Веса для расчета информативности
    SCORE_WEIGHTS = {
        "formula_count": 3.0,
        "key_terms_count": 2.0,
        "word_count_optimal": 2.0,
        "word_count_medium": 1.0,
        "lexical_diversity_high": 1.5,
        "lexical_diversity_medium": 0.7,
        "has_topic": 2.0,
        "has_definitions": 2.5,
        "has_examples": 2.0,
        "sentence_count_optimal": 1.0,
        "topic_relevance_high": 3.0,
        "section_not_intro_conclusion": 1.5,
    }
    
    def __init__(self):
        self.client = GigaChatB2BClient()
        print(f"[OK] Инициализирован B2B клиент")
    
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
                    print(f"  [OK] Точный подсчёт через API выполнен")
                    return [int(r) for r in result]
            return None
        except Exception as e:
            print(f"  [WARN] Ошибка API токенов: {e}")
            return None
    
    def load_pipeline_json(self, json_path: str) -> Dict[str, Any]:
        """Загружает JSON файл от pipeline"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"[OK] Загружен JSON: {json_path}")
            return data
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки JSON: {e}")
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
    
    def select_chunks_accumulate(self, 
                                 pipeline_data: Dict[str, Any],
                                 fill_pct: int = 90) -> Tuple[List[Dict], Dict]:
        """
        Отбирает чанки по стратегии "Ползучее накопление" с умным расширением.
        
        Алгоритм:
        1. Фильтрует некачественные чанки
        2. Сортирует по информативности (score)
        3. Добавляет по одному, пока не заполнит target_limit (fill_pct% от safe_limit)
        4. Если следующий чанк не влезает, проверяется условие на остаток:
           - Если остаток чанка <= 30% от запасного пространства -> добавляем и останавливаемся
           - Если остаток > 30% -> ищем следующий подходящий чанк
        5. Итоговый объём гарантированно <= safe_limit
        """
        chunks = pipeline_data.get('chunks', [])
        
        if not chunks:
            return [], {"error": "Нет чанков для отбора"}
        
        print(f"\n{'='*60}")
        print(f"[СТРАТЕГИЯ] ПОЛЗУЧЕЕ НАКОПЛЕНИЕ (ДО {fill_pct}%)")
        print(f"{'='*60}")
        
        # === ШАГ 1: Фильтрация некачественных чанков ===
        print(f"\n[ШАГ 1] Фильтрация качества...")
        print(f"  * Всего чанков: {len(chunks)}")
        
        passed_chunks = []
        rejected_stats = {}
        
        for i, chunk in enumerate(chunks):
            passed, reason = self._check_chunk_quality(chunk)
            if passed:
                passed_chunks.append({'chunk': chunk, 'index': i})
            else:
                rejected_stats[reason] = rejected_stats.get(reason, 0) + 1
        
        print(f"  * Прошло фильтрацию: {len(passed_chunks)} чанков")
        print(f"  * Отклонено: {len(chunks) - len(passed_chunks)} чанков")
        
        if rejected_stats:
            print(f"  * Причины отклонения:")
            for reason, count in sorted(rejected_stats.items(), 
                                        key=lambda x: -x[1])[:5]:
                print(f"    - {reason}: {count}")
            if len(rejected_stats) > 5:
                print(f"    ... и ещё {len(rejected_stats) - 5} причин")
        
        if not passed_chunks:
            print(f"  [WARN] Все чанки отклонены! Использую все без фильтрации.")
            passed_chunks = [{'chunk': c, 'index': i} 
                           for i, c in enumerate(chunks)]
        
        # === ШАГ 2: Scoring и подсчёт токенов ===
        print(f"\n[ШАГ 2] Оценка информативности и токенов...")
        
        for item in passed_chunks:
            text = item['chunk'].get('processed_text', '')
            item['tokens'] = estimate_tokens_gigachat(text)
            item['score'] = self._calculate_informativeness_score(item['chunk'])
            item['formula_count'] = item['chunk'].get('metadata', {}).get('formula_count', 0)
            item['key_terms'] = item['chunk'].get('metadata', {}).get('key_terms', [])
        
        # Сортируем по убыванию score (самые информативные — первые)
        passed_chunks.sort(key=lambda x: x['score'], reverse=True)
        
        # Статистика
        scores = [item['score'] for item in passed_chunks]
        tokens_list = [item['tokens'] for item in passed_chunks]
        
        if scores:
            print(f"  * Score: мин={min(scores):.1f}, макс={max(scores):.1f}, "
                  f"сред={sum(scores)/len(scores):.1f}")
            print(f"  * Токены: мин={min(tokens_list)}, макс={max(tokens_list)}, "
                  f"сред={sum(tokens_list)//len(tokens_list)}")
        
        # === ШАГ 3: Расчёт лимитов ===
        print(f"\n[ШАГ 3] Расчёт лимитов контекстного окна...")
        
        MAX_CONTEXT = MODEL_CONFIG["context_window"]       # 130 048
        RESPONSE_RESERVE = MODEL_CONFIG["max_output_tokens"]  # 4 096
        PROMPT_OVERHEAD = TOTAL_PROMPT_OVERHEAD            # ~3 400
        SAFETY_FACTOR = 0.8                                 # Коэффициент запаса = 0.8
        
        # Основной безопасный лимит = (контекст - ответ - overhead) * 0.8
        safe_limit = int(
            (MAX_CONTEXT - RESPONSE_RESERVE - PROMPT_OVERHEAD) * SAFETY_FACTOR
        )
        
        # Целевой порог = fill_pct% от безопасного лимита
        target_limit = int(safe_limit * fill_pct / 100)
        
        # Запасное пространство = безопасный лимит - целевой порог
        buffer_space = safe_limit - target_limit
        
        print(f"  * Контекст GigaChat: {MAX_CONTEXT:,} токенов")
        print(f"  * Резерв на ответ: {RESPONSE_RESERVE:,} токенов")
        print(f"  * Накладные расходы: {PROMPT_OVERHEAD:,} токенов")
        print(f"  * Коэффициент запаса: {SAFETY_FACTOR}")
        print(f"  * Безопасный лимит: {safe_limit:,} токенов")
        print(f"  * Целевой порог ({fill_pct}%): {target_limit:,} токенов")
        print(f"  * Запасное пространство: {buffer_space:,} токенов")
        print(f"  * Порог расширения (30% от запаса): {int(buffer_space * 0.3):,} токенов")
        
        # === ШАГ 4: Ползучее накопление с умным расширением ===
        print(f"\n[ШАГ 4] Ползучее накопление с умным расширением...")
        print(f"  Добавляем чанки по одному...")
        
        selected = []
        selected_tokens = 0
        formulas_covered = 0
        terms_covered = set()
        chunk_count = 0
        expansion_used = False
        final_limit_used = target_limit
        
        total_formulas = sum(item['formula_count'] for item in passed_chunks)
        all_terms = set()
        for item in passed_chunks:
            all_terms.update(item['key_terms'])
        
        i = 0
        while i < len(passed_chunks):
            item = passed_chunks[i]
            i += 1
            
            # Проверяем: если добавим этот чанк, не превысим ли целевой порог?
            if selected_tokens + item['tokens'] <= target_limit:
                # Случай 1: Фрагмент полностью помещается в целевой порог
                selected.append(item['chunk'])
                selected_tokens += item['tokens']
                formulas_covered += item['formula_count']
                terms_covered.update(item['key_terms'])
                chunk_count += 1
                
                progress_pct = selected_tokens / target_limit * 100 if target_limit > 0 else 0
                if chunk_count % 10 == 0 or progress_pct >= 90:
                    print(f"  * Чанк {i}: добавлен полностью "
                          f"({item['tokens']} ток, score={item['score']:.1f}) | "
                          f"Всего: {selected_tokens:,}/{target_limit:,} ток "
                          f"({progress_pct:.0f}%)")
            else:
                # Случай 2: Фрагмент не помещается в целевой порог
                # Вычисляем остаток (часть, которая не влезает)
                overflow = (selected_tokens + item['tokens']) - target_limit
                overflow_pct = (overflow / buffer_space * 100) if buffer_space > 0 else 100
                
                print(f"  * Чанк {i}: не влезает в целевой порог")
                print(f"    - Размер чанка: {item['tokens']} ток")
                print(f"    - Остаток сверх порога: {overflow} ток")
                print(f"    - Остаток от запаса: {overflow_pct:.1f}%")
                
                # Проверяем условие для расширения: остаток <= 30% от запасного пространства
                if not expansion_used and overflow <= buffer_space * 0.3:
                    # Расширяем границу и добавляем фрагмент
                    final_limit_used = selected_tokens + item['tokens']
                    selected.append(item['chunk'])
                    selected_tokens += item['tokens']
                    formulas_covered += item['formula_count']
                    terms_covered.update(item['key_terms'])
                    chunk_count += 1
                    expansion_used = True
                    
                    print(f"  [OK] Чанк {i}: ДОБАВЛЕН с РАСШИРЕНИЕМ")
                    print(f"     * Остаток ({overflow} ток) <= 30% от запаса ({int(buffer_space * 0.3)} ток)")
                    print(f"     * Новый лимит: {selected_tokens:,} ток (в пределах safe_limit={safe_limit:,})")
                    break  # Останавливаемся после добавления
                else:
                    # Случай 3: Остаток слишком большой - ищем следующий подходящий чанк
                    if expansion_used:
                        print(f"  * Расширение уже использовано, пропускаем чанк {i}")
                    else:
                        reason = f"остаток ({overflow} ток) > 30% от запаса ({int(buffer_space * 0.3)} ток)"
                        print(f"  [SKIP] Пропускаем чанк {i}: {reason}")
                    
                    # Продолжаем поиск подходящего чанка среди оставшихся
                    continue
        
        # Если вышли из цикла, но не использовали расширение - достигли целевого порога или кончились чанки
        if not expansion_used:
            if selected_tokens >= target_limit:
                print(f"\n  [OK] Достигнут целевой порог {target_limit:,} токенов")
            else:
                print(f"\n  [INFO] Закончились чанки, набрано {selected_tokens:,} из {target_limit:,} токенов")
        
        # === ШАГ 5: Статистика ===
        fill_percentage = (selected_tokens / safe_limit * 100) if safe_limit else 0
        target_achieved_pct = (selected_tokens / target_limit * 100) if target_limit else 0
        formulas_pct = (formulas_covered / total_formulas * 100) if total_formulas else 100
        terms_pct = (len(terms_covered) / len(all_terms) * 100) if all_terms else 100
        
        # Считаем средний score отобранных
        selected_scores = [item['score'] for item in passed_chunks[:len(selected)]]
        avg_score = sum(selected_scores) / len(selected_scores) if selected_scores else 0
        
        selection_info = {
            "total_chunks_in_file": len(chunks),
            "passed_filter": len(passed_chunks),
            "rejected": len(chunks) - len(passed_chunks),
            "selected_count": len(selected),
            "selected_tokens": selected_tokens,
            "target_limit": target_limit,
            "safe_limit": safe_limit,
            "buffer_space": buffer_space,
            "fill_percentage": round(fill_percentage, 1),
            "target_achieved_pct": round(target_achieved_pct, 1),
            "target_fill_pct": fill_pct,
            "expansion_used": expansion_used,
            "final_limit_used": final_limit_used,
            "total_formulas": total_formulas,
            "formulas_covered": formulas_covered,
            "formulas_coverage_pct": round(formulas_pct, 1),
            "total_unique_terms": len(all_terms),
            "terms_covered": len(terms_covered),
            "terms_coverage_pct": round(terms_pct, 1),
            "avg_score": round(avg_score, 1),
            "max_score": max(scores) if scores else 0,
            "strategy": "accumulate_with_smart_expansion"
        }
        
        print(f"\n{'='*60}")
        print(f"[РЕЗУЛЬТАТ] ПОЛЗУЧЕЕ НАКОПЛЕНИЕ")
        print(f"{'='*60}")
        print(f"  * Отобрано чанков: {len(selected)}")
        print(f"  * Заполнение безопасного лимита: {selected_tokens:,} из {safe_limit:,} ток "
              f"({fill_percentage:.1f}%)")
        print(f"  * Достижение целевого порога: {target_achieved_pct:.1f}% ({selected_tokens:,}/{target_limit:,})")
        print(f"  * Использовано расширение: {'ДА' if expansion_used else 'НЕТ'}")
        print(f"  * Средний score: {avg_score:.1f}")
        print(f"  * Покрытие формул: {formulas_pct:.1f}%")
        print(f"  * Покрытие терминов: {terms_pct:.1f}%")
        
        if not expansion_used and target_achieved_pct < fill_pct - 5:
            print(f"  [WARN] Не достигнут целевой порог (не хватило чанков)")
        
        if expansion_used:
            print(f"  [OK] Расширение использовано корректно, safe_limit не превышен")
        
        return selected, selection_info
    
    def extract_text_from_chunks(self, selected_chunks: List[Dict]) -> List[str]:
        """Извлекает текст из отобранных чанков"""
        texts = []
        for chunk in selected_chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        
        print(f"\n[INFO] Извлечено {len(texts)} текстовых блоков")
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
- Отобрано {selection_info['selected_count']} наиболее информативных фрагментов
- Стратегия: ползучее накопление до {selection_info.get('target_fill_pct', 90)}% контекста
- Заполнение: {selection_info.get('fill_percentage', 0)}%
- Средний score: {selection_info.get('avg_score', 0)}
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
    
    async def process_pipeline_json(self, json_path: str, 
                                    num_questions: int = 10,
                                    fill_pct: int = 90) -> Dict[str, Any]:
        """Основной метод обработки"""
        
        print("=" * 70)
        print(f"[ОБРАБОТКА] JSON: ПОЛЗУЧЕЕ НАКОПЛЕНИЕ (ДО {fill_pct}%)")
        print("=" * 70)
        
        # 1. Загружаем JSON
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        # 2. Отбираем чанки ползучим накоплением
        selected_chunks, selection_info = self.select_chunks_accumulate(
            pipeline_data, fill_pct
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
        print(f"\n[МЕТАДАННЫЕ]:")
        print(f"  * Файл: {metadata['source_file']}")
        print(f"  * Чанков в файле: {metadata['total_chunks']}")
        print(f"  * Отобрано: {len(selected_chunks)}")
        
        # 5. Создаем промпт
        prompt = self.create_prompt(texts, num_questions, selection_info)
        
        # 6. Финальная проверка размера
        print(f"\n[ФИНАЛЬНАЯ ПРОВЕРКА]:")
        print(f"  * Размер промпта: {len(prompt):,} символов")
        
        final_tokens = estimate_tokens_gigachat(prompt)
        print(f"  * Токенов (оценка): {final_tokens:,}")
        print(f"  * Лимит GigaChat: {MODEL_CONFIG['context_window']:,}")
        
        context_fill = final_tokens / MODEL_CONFIG['context_window'] * 100
        print(f"  * Заполнение контекста: {context_fill:.1f}%")
        
        if context_fill > 95:
            print(f"  [WARN] Превышен безопасный порог 95%!")
        
        # 7. Отправляем в GigaChat
        print(f"\n[ОТПРАВКА] Отправка в GigaChat...")
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f"[OK] Ответ получен")
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
                print("  [OK] JSON успешно распарсен")
            except json.JSONDecodeError as e:
                print(f"  [WARN] Ошибка JSON: {e}")
                try:
                    cleaned = clean_json_for_parsing(json_str)
                    test_result = json.loads(cleaned)
                    print("  [OK] JSON распарсен после очистки LaTeX")
                except:
                    test_result = {"raw_response": content, "questions": []}
            
            # Добавляем метаданные
            test_result['pipeline_metadata'] = metadata
            test_result['selection_info'] = selection_info
            test_result['token_stats'] = {
                'final_prompt_tokens': final_tokens,
                'context_fill_pct': round(context_fill, 1),
                'texts_used': len(texts),
                'prompt_chars': len(prompt)
            }
            
            return test_result
            
        except Exception as e:
            print(f"[ERROR] Ошибка: {e}")
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
            print(f"[SAVE] Сырой ответ сохранён: {raw_path}")
        
        try:
            serializable_result = json.loads(
                json.dumps(result, ensure_ascii=False, default=str)
            )
        except:
            serializable_result = result
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_result, f, ensure_ascii=False, indent=2)
        
        print(f"[SAVE] Результат сохранён: {output_path}")
        return output_path


async def main():
    """Основная функция"""
    
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    if not Path(json_file).exists():
        print(f"[ERROR] Файл не найден: {json_file}")
        current_dir = Path(__file__).parent
        possible_files = list(current_dir.glob("*.json"))
        if possible_files:
            print(f"\n[INFO] Найденные JSON файлы:")
            for f in possible_files:
                print(f"  * {f}")
            json_file = str(possible_files[0])
            print(f"\n[INFO] Использую: {json_file}")
        else:
            return
    
    processor = PipelineJSONProcessor()
    
    result = await processor.process_pipeline_json(
        json_path=json_file,
        num_questions=10,
        fill_pct=90
    )
    
    if 'error' not in result:
        output_file = processor.save_result(result)
        
        print("\n" + "=" * 70)
        print("[РЕЗУЛЬТАТ] ГЕНЕРАЦИЯ ТЕСТА")
        print("=" * 70)
        print(f"Название: {result.get('test_title', 'N/A')}")
        print(f"Тема: {result.get('subject', 'N/A')}")
        print(f"Вопросов: {len(result.get('questions', []))}")
        
        selection_info = result.get('selection_info', {})
        if selection_info:
            print(f"\n[СТАТИСТИКА НАКОПЛЕНИЯ]:")
            print(f"  * Стратегия: {selection_info.get('strategy', 'N/A')}")
            print(f"  * Отобрано: {selection_info['selected_count']} чанков")
            print(f"  * Заполнение: {selection_info.get('fill_percentage', 0)}%")
            print(f"  * Средний score: {selection_info.get('avg_score', 0)}")
            print(f"  * Покрытие формул: {selection_info['formulas_coverage_pct']}%")
            print(f"  * Покрытие терминов: {selection_info['terms_coverage_pct']}%")
        
        token_stats = result.get('token_stats', {})
        if token_stats:
            print(f"\n[ТОКЕНЫ]:")
            print(f"  * В промпте: {token_stats.get('final_prompt_tokens', 0):,}")
            print(f"  * Заполнение контекста: {token_stats.get('context_fill_pct', 0)}%")
        
        if result.get('questions'):
            q = result['questions'][0]
            print(f"\n[ПРИМЕР ВОПРОСА]:")
            print(f"  {q.get('question', '')}")
            print(f"  Варианты: {q.get('options', [])}")
            print(f"  Ответ: {q.get('correct_answer', '')}")
    else:
        print(f"\n[ERROR] Ошибка: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
