"""
Кластеризация по ключевым темам (Topic Clustering Strategy)
Для очень больших файлов: выбираем 2-3 главные темы и собираем связанные чанки.
"""
import json
import asyncio
import sys
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict, Counter

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
    """Обработчик JSON файлов с кластеризацией по темам"""
    
    REJECT_CRITERIA = {
        "min_word_count": 10,
        "min_key_terms": 1,
        "max_placeholder_ratio": 0.7,
        "min_clean_text_chars": 20,
    }
    
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
        print(f" Инициализирован B2B клиент")
    
    def load_pipeline_json(self, json_path: str) -> Dict[str, Any]:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f" Загружен JSON: {json_path}")
            return data
        except Exception as e:
            print(f" Ошибка загрузки JSON: {e}")
            return {}
    
    def _calculate_placeholder_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        formulas = re.findall(r'\[\[FORMULA_[^\]]+\]\]', text)
        formula_chars = sum(len(f) for f in formulas)
        return formula_chars / len(text) if len(text) > 0 else 0.0
    
    def _check_chunk_quality(self, chunk: Dict) -> Tuple[bool, str]:
        text = chunk.get('processed_text', '')
        metadata = chunk.get('metadata', {})
        
        word_count = metadata.get('word_count', 0)
        if word_count < self.REJECT_CRITERIA['min_word_count']:
            return False, f"word_count={word_count}"
        
        key_terms = metadata.get('key_terms', [])
        if len(key_terms) < self.REJECT_CRITERIA['min_key_terms']:
            return False, "key_terms пуст"
        
        placeholder_ratio = self._calculate_placeholder_ratio(text)
        if placeholder_ratio > self.REJECT_CRITERIA['max_placeholder_ratio']:
            return False, f"placeholder_ratio={placeholder_ratio:.2f}"
        
        clean_text = re.sub(r'\[\[FORMULA_[^\]]+\]\]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if len(clean_text) < self.REJECT_CRITERIA['min_clean_text_chars']:
            return False, f"clean_text={len(clean_text)} chars"
        
        return True, "OK"
    
    def _calculate_informativeness_score(self, chunk: Dict) -> float:
        metadata = chunk.get('metadata', {})
        score = 0.0
        
        formula_count = metadata.get('formula_count', 0)
        score += formula_count * self.SCORE_WEIGHTS['formula_count']
        
        key_terms = metadata.get('key_terms', [])
        score += len(key_terms) * self.SCORE_WEIGHTS['key_terms_count']
        
        word_count = metadata.get('word_count', 0)
        if 20 <= word_count <= 300:
            score += self.SCORE_WEIGHTS['word_count_optimal']
        elif 10 <= word_count <= 500:
            score += self.SCORE_WEIGHTS['word_count_medium']
        
        lexical_diversity = metadata.get('lexical_diversity', 0)
        if lexical_diversity > 0.4:
            score += self.SCORE_WEIGHTS['lexical_diversity_high']
        elif lexical_diversity > 0.3:
            score += self.SCORE_WEIGHTS['lexical_diversity_medium']
        
        main_topic = metadata.get('main_topic', '')
        if main_topic and main_topic not in ['неизвестно', 'unknown', '']:
            score += self.SCORE_WEIGHTS['has_topic']
        
        if metadata.get('has_definitions', False):
            score += self.SCORE_WEIGHTS['has_definitions']
        
        if metadata.get('has_examples', False):
            score += self.SCORE_WEIGHTS['has_examples']
        
        sentence_count = metadata.get('sentence_count', 0)
        if 3 <= sentence_count <= 15:
            score += self.SCORE_WEIGHTS['sentence_count_optimal']
        
        topic_relevance = metadata.get('topic_relevance', 0)
        if topic_relevance > 0.5:
            score += self.SCORE_WEIGHTS['topic_relevance_high']
        
        section_type = metadata.get('section_type', '')
        if section_type and section_type not in ['введение', 'заключение', 
                                                   'introduction', 'conclusion']:
            score += self.SCORE_WEIGHTS['section_not_intro_conclusion']
        
        return score
    
    def _extract_main_topics(self, prepared_chunks: List[Dict], 
                             num_topics: int = 3) -> List[Dict]:
        """
        Определяет главные темы документа.
        
        Критерии выбора тем:
        1. Частотность (сколько чанков относятся к теме)
        2. Суммарный score чанков темы
        3. Количество формул в теме
        4. Разнообразие ключевых терминов
        """
        # Группируем чанки по main_topic
        topic_groups = defaultdict(list)
        no_topic_chunks = []
        
        for item in prepared_chunks:
            topic = item.get('main_topic', '')
            if topic and topic not in ['неизвестно', 'unknown', '']:
                topic_groups[topic].append(item)
            else:
                no_topic_chunks.append(item)
        
        print(f"\n АНАЛИЗ ТЕМ:")
        print(f"  Найдено тем: {len(topic_groups)}")
        print(f"  Чанков без темы: {len(no_topic_chunks)}")
        
        # Считаем метрики для каждой темы
        topic_stats = []
        for topic, items in topic_groups.items():
            total_score = sum(item['score'] for item in items)
            total_formulas = sum(item.get('formula_count', 0) for item in items)
            total_tokens = sum(item['tokens'] for item in items)
            
            # Собираем уникальные термины темы
            topic_terms = set()
            for item in items:
                topic_terms.update(item.get('key_terms', []))
            
            topic_stats.append({
                'topic': topic,
                'chunk_count': len(items),
                'total_score': total_score,
                'total_formulas': total_formulas,
                'total_tokens': total_tokens,
                'unique_terms': len(topic_terms),
                'items': items
            })
        
        # Сортируем по важности (комбинированный рейтинг)
        for stat in topic_stats:
            # Нормализуем метрики
            stat['importance'] = (
                stat['chunk_count'] * 0.3 +          # Частотность
                stat['total_score'] * 0.3 +           # Качество
                stat['total_formulas'] * 0.2 +        # Формулы
                stat['unique_terms'] * 0.2            # Разнообразие терминов
            )
        
        topic_stats.sort(key=lambda x: x['importance'], reverse=True)
        
        # Выбираем top-N тем
        main_topics = topic_stats[:num_topics]
        
        print(f"\n ТОП-{num_topics} Главных тем:")
        for i, stat in enumerate(main_topics, 1):
            print(f"  {i}. «{stat['topic']}»")
            print(f"     Чанков: {stat['chunk_count']} | "
                  f"Score: {stat['total_score']:.0f} | "
                  f"Формул: {stat['total_formulas']} | "
                  f"Терминов: {stat['unique_terms']} | "
                  f"Токенов: {stat['total_tokens']:,}")
        
        # Показываем остальные темы
        other_topics = topic_stats[num_topics:]
        if other_topics:
            print(f"\n  Остальные темы ({len(other_topics)}):")
            for stat in other_topics[:5]:
                print(f"    - «{stat['topic']}»: {stat['chunk_count']} чанков")
            if len(other_topics) > 5:
                print(f" и ещё {len(other_topics) - 5} тем")
        
        # Чанки без темы добавляем к последней теме или создаём группу "общее"
        if no_topic_chunks:
            # Распределяем чанки без темы по ключевым терминам
            main_terms = set()
            for stat in main_topics:
                for item in stat['items']:
                    main_terms.update(item.get('key_terms', []))
            
            # Привязываем к теме, с которой больше всего общих терминов
            for item in no_topic_chunks:
                item_terms = set(item.get('key_terms', []))
                best_topic_idx = 0
                best_overlap = 0
                
                for idx, stat in enumerate(main_topics):
                    topic_terms = set()
                    for t_item in stat['items']:
                        topic_terms.update(t_item.get('key_terms', []))
                    overlap = len(item_terms & topic_terms)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_topic_idx = idx
                
                if best_overlap > 0:
                    main_topics[best_topic_idx]['items'].append(item)
                    main_topics[best_topic_idx]['chunk_count'] += 1
        
        return main_topics
    
    def select_chunks_topic_clustering(self, 
                                       pipeline_data: Dict[str, Any],
                                       num_topics: int = 3,
                                       fill_pct: int = 90) -> Tuple[List[Dict], Dict]:
        """
        Отбирает чанки по стратегии кластеризации по темам.
        
        Алгоритм:
        1. Определяет 2-3 главные темы документа
        2. Распределяет доступные токены пропорционально важности тем
        3. Внутри каждой темы отбирает лучшие чанки (ползучее накопление)
        4. Объединяет чанки из всех выбранных тем
        """
        chunks = pipeline_data.get('chunks', [])
        
        if not chunks:
            return [], {"error": "Нет чанков для отбора"}
        
        
        print(f" ОТБОР ЧАНКОВ: КЛАСТЕРИЗАЦИЯ ПО ТЕМАМ")
        
        print(f"\n ШАГ 1: Подготовка и фильтрация чанков...")
        print(f"  Всего чанков: {len(chunks)}")
        
        prepared = []
        rejected_stats = {}
        
        for i, chunk in enumerate(chunks):
            passed, reason = self._check_chunk_quality(chunk)
            if passed:
                text = chunk.get('processed_text', '')
                prepared.append({
                    'chunk': chunk,
                    'index': i,
                    'tokens': estimate_tokens_gigachat(text),
                    'score': self._calculate_informativeness_score(chunk),
                    'formula_count': chunk.get('metadata', {}).get('formula_count', 0),
                    'key_terms': chunk.get('metadata', {}).get('key_terms', []),
                    'main_topic': chunk.get('metadata', {}).get('main_topic', ''),
                    'word_count': chunk.get('metadata', {}).get('word_count', 0),
                })
            else:
                rejected_stats[reason] = rejected_stats.get(reason, 0) + 1
        
        print(f"  Прошло фильтрацию: {len(prepared)} чанков")
        print(f"  Отклонено: {len(chunks) - len(prepared)} чанков")
        
        if not prepared:
            return [], {"error": "Все чанки отклонены"}
        
        # === ШАГ 2: Определение главных тем ===
        print(f"\n  ШАГ 2: Определение главных тем.")
        main_topics = self._extract_main_topics(prepared, num_topics)
        
        if not main_topics:
            return [], {"error": "Не удалось определить темы"}
        
        # === ШАГ 3: Расчёт лимита токенов ===
        print(f"\n ШАГ 3: Расчёт лимитов.")
        
        MAX_CONTEXT = MODEL_CONFIG["context_window"]
        RESPONSE_RESERVE = MODEL_CONFIG["max_output_tokens"]
        PROMPT_OVERHEAD = TOTAL_PROMPT_OVERHEAD + 2_000
        SAFETY_MARGIN = 0.90
        
        available_tokens = int(
            (MAX_CONTEXT - RESPONSE_RESERVE - PROMPT_OVERHEAD) * SAFETY_MARGIN
        )
        
        target_tokens = int(available_tokens * fill_pct / 100)
        
        print(f"  Доступно токенов: {available_tokens:,}")
        print(f"  Целевой лимит ({fill_pct}%): {target_tokens:,}")
        
        # === ШАГ 4: Распределение токенов между темами ===
        print(f"\n ШАГ 4: Распределение токенов между темами.")
        
        # Считаем общую важность
        total_importance = sum(stat['importance'] for stat in main_topics)
        
        for stat in main_topics:
            # Пропорциональное распределение
            stat['token_budget'] = int(
                target_tokens * stat['importance'] / total_importance
            )
            # Сортируем чанки внутри темы по score
            stat['items'].sort(key=lambda x: x['score'], reverse=True)
            
            print(f"  • «{stat['topic']}»: {stat['token_budget']:,} токенов "
                  f"({stat['importance']/total_importance*100:.0f}%)")
        
        # === ШАГ 5: Отбор чанков внутри каждой темы ===
        print(f"\n ШАГ 5: Ползучее накопление внутри тем.")
        
        all_selected = []
        total_formulas = sum(
            stat['total_formulas'] for stat in main_topics
        )
        total_unique_terms = set()
        for stat in main_topics:
            for item in stat['items']:
                total_unique_terms.update(item.get('key_terms', []))
        
        covered_formulas = 0
        covered_terms = set()
        total_selected_tokens = 0
        
        for stat in main_topics:
            topic_selected = []
            topic_tokens = 0
            
            print(f"\n Тема «{stat['topic']}» (бюджет: {stat['token_budget']:,} ток):")
            
            for i, item in enumerate(stat['items'], 1):
                if topic_tokens + item['tokens'] > stat['token_budget']:
                    remaining = stat['token_budget'] - topic_tokens
                    if remaining > item['tokens'] * 0.3:
                        topic_selected.append(item)
                        topic_tokens += item['tokens']
                    break
                
                topic_selected.append(item)
                topic_tokens += item['tokens']
                
                if i % 5 == 0 or i == 1 or topic_tokens >= stat['token_budget'] * 0.9:
                    progress = topic_tokens / stat['token_budget'] * 100
                    print(f"    Чанк {i}: +{item['tokens']} ток "
                          f"(score={item['score']:.0f}) | "
                          f"Всего: {topic_tokens:,} ток ({progress:.0f}%)")
            
            # Собираем статистику
            for item in topic_selected:
                covered_formulas += item.get('formula_count', 0)
                covered_terms.update(item.get('key_terms', []))
            
            all_selected.extend([item['chunk'] for item in topic_selected])
            total_selected_tokens += topic_tokens
            
            print(f"  Отобрано: {len(topic_selected)} чанков, "
                  f"{topic_tokens:,} токенов")
        
        # === ШАГ 6: Статистика ===
        formulas_pct = (covered_formulas / total_formulas * 100) if total_formulas else 100
        terms_pct = (len(covered_terms) / len(total_unique_terms) * 100) if total_unique_terms else 100
        
        selection_info = {
            "total_chunks_in_file": len(chunks),
            "passed_filter": len(prepared),
            "rejected": len(chunks) - len(prepared),
            "num_topics_selected": len(main_topics),
            "selected_topics": [stat['topic'] for stat in main_topics],
            "selected_count": len(all_selected),
            "selected_tokens": total_selected_tokens,
            "target_tokens": target_tokens,
            "available_tokens": available_tokens,
            "fill_percentage": round(total_selected_tokens / available_tokens * 100, 1),
            "total_formulas": total_formulas,
            "formulas_covered": covered_formulas,
            "formulas_coverage_pct": round(formulas_pct, 1),
            "total_unique_terms": len(total_unique_terms),
            "terms_covered": len(covered_terms),
            "terms_coverage_pct": round(terms_pct, 1),
            "strategy": "topic_clustering",
            "topic_details": [
                {
                    "topic": stat['topic'],
                    "chunks_selected": len([item for item in stat['items'] 
                                           if item['chunk'] in all_selected]),
                    "token_budget": stat['token_budget'],
                    "importance": round(stat['importance'], 1)
                }
                for stat in main_topics
            ]
        }
        
     
        print(f" РЕЗУЛЬТАТ КЛАСТЕРИЗАЦИИ")
        print(f"  Выбрано тем: {len(main_topics)}")
        for detail in selection_info['topic_details']:
            print(f"    - «{detail['topic']}»: {detail['chunks_selected']} чанков, "
                  f"важность {detail['importance']:.0f}")
        print(f"  Всего чанков: {len(all_selected)}")
        print(f"  Заполнение: {total_selected_tokens:,} из {available_tokens:,} "
              f"({selection_info['fill_percentage']}%)")
        print(f"  Покрытие формул: {formulas_pct:.1f}%")
        print(f"  Покрытие терминов: {terms_pct:.1f}%")
        
        return all_selected, selection_info
    
    def extract_text_from_chunks(self, selected_chunks: List[Dict]) -> List[str]:
        texts = []
        for chunk in selected_chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        print(f"\n Извлечено {len(texts)} текстовых блоков")
        return texts
    
    def get_metadata(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'source_file': pipeline_data.get('source_file', 'unknown'),
            'process_id': pipeline_data.get('process_id', 'unknown'),
            'processed_at': pipeline_data.get('processed_at', 'unknown'),
            'statistics': pipeline_data.get('statistics', {}),
            'total_chunks': len(pipeline_data.get('chunks', []))
        }
    
    def create_prompt(self, texts: List[str], num_questions: int = 10,
                      selection_info: Dict = None) -> str:
        context = "\n\n".join(texts)
        
        coverage_note = ""
        if selection_info:
            topics_str = ", ".join(selection_info.get('selected_topics', []))
            coverage_note = f"""
ИНФОРМАЦИЯ О МАТЕРИАЛЕ:
- Стратегия: кластеризация по {selection_info.get('num_topics_selected', 0)} главным темам
- Темы: {topics_str}
- Отобрано {selection_info['selected_count']} связанных фрагментов
- Покрытие формул: {selection_info['formulas_coverage_pct']}%
- Покрытие ключевых терминов: {selection_info['terms_coverage_pct']}%
"""
        
        prompt = f""" ТВОЯ ЗАДАЧА: Создать тест из {num_questions} вопросов.

🚨 КЛЮЧЕВОЕ ТРЕБОВАНИЕ: ИЗБЕГАЙ перечисленных ниже ОШИБОК и ПЛОХИХ ПРИМЕРОВ.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌❌❌ ЗАПРЕЩЕННЫЕ ПАТТЕРНЫ (НИКОГДА НЕ ИСПОЛЬЗУЙ) ❌❌❌

1. ❌ Вопросы типа "Все вышеперечисленное верно"
   ПЛОХО: "Что верно про X? А) ... Б) ... В) ... Г) Все вышеперечисленное"
   ПОЧЕМУ: Слишком легко угадать, не проверяет реальное понимание

2. ❌ Вопросы с двойным отрицанием
   ПЛОХО: "Что НЕ является НЕверным утверждением о Y?"
   ПОЧЕМУ: Путает студентов, проверяет логику, а не знание материала

3. ❌ Дословное копирование из материала
   ПЛОХО: Вопрос в точности повторяет предложение из текста
   ПОЧЕМУ: Проверяет память, а не понимание

4. ❌ Слишком очевидные дистракторы
   ПЛОХО: "Что такое фотон? А) Кошка Б) Частица света В) Машина Г) Дом"
   ПОЧЕМУ: Не заставляют думать, легко отбросить нелепые варианты

5. ❌ Неоднозначные вопросы
   ПЛОХО: "Как работает двигатель?" (слишком широко)
   ПОЧЕМУ: Много возможных правильных ответов

6. ❌ Вопросы, на которые можно ответить без материала
   ПЛОХО: "Что тяжелее: 1 кг ваты или 1 кг железа?"
   ПОЧЕМУ: Общие знания, не связанные с материалом

7. ❌ Вариант "А и Б" или "Б и В"
   ПЛОХО: "Какие из утверждений верны: А) ... Б) ... В) ... Г) А и Б"
   ПОЧЕМУ: Сложно автоматически проверять, двусмысленность

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅✅✅ ХОРОШИЕ ПАТТЕРНЫ (делай ТАК) ✅✅✅

1. ✅ Вопросы на сравнение: "Чем отличается X от Y?"
2. ✅ Вопросы на применение: "Если произойдет Z, то что будет?"
3. ✅ Вопросы на анализ: "Почему верно утверждение W?"
4. ✅ Дистракторы на основе реальных ошибок понимания
5. ✅ Конкретные, измеримые вопросы
6. ✅ Варианты, которые все правдоподобны, но только один точен
7. Использования формул из исходных материалов. 

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📄 ИСХОДНЫЙ МАТЕРИАЛ (ТОЛЬКО ИЗ НЕГО БРАТЬ ФАКТЫ):

{context}

{coverage_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 ПРОВЕРОЧНЫЙ ЧЕК-ЛИСТ (перед выводом проверь каждый вопрос):

[ ] Вопрос НЕ содержит "все вышеперечисленное"
[ ] Вопрос НЕ содержит двойных отрицаний
[ ] Вопрос НЕ скопирован дословно из материала
[ ] Все 4 варианта правдоподобны (нет абсурдных)
[ ] Вопрос однозначен и конкретен
[ ] На вопрос НЕЛЬЗЯ ответить без материала
[ ] Нет вариантов типа "А и Б"
[ ] Пояснение объясняет, ПОЧЕМУ правильный ответ верен

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

СОЗДАЙ ТЕСТ из {num_questions} вопросов, строго следуя ХОРОШИМ паттернам и избегая ПЛОХИХ:

{{
    "test_title": "...",
    "generation_method": "Negative_Prompting",
    "validation_checks_passed": {num_questions},
    "questions": [
        {{
            "id": 1,
            "question": "...",
            "options": ["...", "...", "...", "..."],
            "correct_answer": "...",
            "explanation": "...",
            "why_not_bad": "краткое объяснение, почему этот вопрос не нарушает запреты"
        }}
    ]
}}
"""
        return prompt
    
    async def process_pipeline_json(self, json_path: str,
                                    num_questions: int = 10,
                                    num_topics: int = 3,
                                    fill_pct: int = 90) -> Dict[str, Any]:
        """Основной метод обработки с кластеризацией по темам"""
        
        
        print(f" ОБРАБОТКА JSON: Кластерилизация по {num_topics} темам")
                
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        selected_chunks, selection_info = self.select_chunks_topic_clustering(
            pipeline_data, num_topics, fill_pct
        )
        
        if not selected_chunks:
            return {"error": "Не удалось отобрать чанки",
                    "selection_info": selection_info}
        
        texts = self.extract_text_from_chunks(selected_chunks)
        if not texts:
            return {"error": "Нет текстов для обработки"}
        
        metadata = self.get_metadata(pipeline_data)
        print(f"\n Метаданные:")
        print(f"  Файл: {metadata['source_file']}")
        print(f"  Чанков в файле: {metadata['total_chunks']}")
        print(f"  Отобрано: {len(selected_chunks)}")
        
        prompt = self.create_prompt(texts, num_questions, selection_info)
        
        print(f"\n ФИНАЛЬНАЯ ПРОВЕРКА:")
        final_tokens = estimate_tokens_gigachat(prompt)
        print(f"   Размер промпта: {len(prompt):,} символов")
        print(f"   Токенов: {final_tokens:,}")
        
        print(f"\n  Отправка в GigaChat.")
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f" Ответ получен")
            content = response['choices'][0]['message']['content']
            
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
            
            test_result = None
            try:
                test_result = json.loads(json_str)
                print("   JSON успешно распарсен")
            except json.JSONDecodeError:
                try:
                    cleaned = clean_json_for_parsing(json_str)
                    test_result = json.loads(cleaned)
                    print(" JSON распарсен после очистки LaTeX")
                except:
                    test_result = {"raw_response": content, "questions": []}
            
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
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"test_result_{timestamp}.json"
        
        if "raw_response" in result:
            raw_path = output_path.replace('.json', '_raw.txt')
            with open(raw_path, 'w', encoding='utf-8') as f:
                f.write(result["raw_response"])
            print(f" Сырой ответ сохранён: {raw_path}")
        
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
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    if not Path(json_file).exists():
        print(f" Файл не найден: {json_file}")
        return
    
    processor = PipelineJSONProcessor()
    
    result = await processor.process_pipeline_json(
        json_path=json_file,
        num_questions=10,
        num_topics=3,   # Выбрать 3 главные темы
        fill_pct=90     # Заполнить до 90% контекста
    )
    
    if 'error' not in result:
        output_file = processor.save_result(result)
        
        
        print(" Результат генерации теста")
                
        selection_info = result.get('selection_info', {})
        if selection_info:
            print(f"\n СТАТИСТИКА КЛАСТЕРИЗАЦИИ:")
            print(f"  Главные темы: {', '.join(selection_info.get('selected_topics', []))}")
            print(f"  Отобрано чанков: {selection_info['selected_count']}")
            print(f"  Заполнение: {selection_info.get('fill_percentage', 0)}%")


if __name__ == "__main__":
    asyncio.run(main())
