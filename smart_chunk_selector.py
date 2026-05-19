"""
smart_chunk_selector.py
Отбор наиболее информативных чанков по принципу "Топ по информативности".
Строгие критерии качества + расчет лимита токенов.
"""
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chunk_range_calculator import (
    estimate_tokens_gigachat,
    MODEL_CONFIG,
    TOTAL_PROMPT_OVERHEAD
)


class SmartChunkSelector:
    """
    Интеллектуальный отбор чанков по строгим критериям информативности.
    """
    
    # Критерии отклонения (обязательные)
    REJECT_CRITERIA = {
        "min_word_count": 10,           # Минимум слов
        "min_key_terms": 1,             # Минимум ключевых терминов
        "require_formulas": False,       # Требовать формулы (опционально)
        "min_formula_count": 0,         # Минимум формул
        "max_placeholder_ratio": 0.7,   # Максимум % формульных плейсхолдеров в тексте
    }
    
    # Веса для scoring (важные критерии)
    SCORE_WEIGHTS = {
        "formula_count": 3.0,           # Каждая формула
        "key_terms_count": 2.0,         # Каждый ключевой термин
        "word_count_optimal": 2.0,      # Оптимальный размер (20-300 слов)
        "lexical_diversity": 1.5,       # Лексическое разнообразие > 0.4
        "has_topic": 2.0,               # Определена тема
        "has_definitions": 2.5,         # Содержит определения
        "has_examples": 2.0,            # Содержит примеры
        "sentence_count_optimal": 1.0,  # Оптимальное количество предложений
    }
    
    def __init__(self, json_path: str):
        """Загружает JSON и готовит данные"""
        self.json_path = json_path
        self.data = self._load_json()
        self.chunks = self.data.get('chunks', [])
        print(f"📁 Загружено чанков: {len(self.chunks)}")
    
    def _load_json(self) -> Dict[str, Any]:
        """Загружает JSON файл"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _calculate_placeholder_ratio(self, text: str) -> float:
        """
        Вычисляет долю формульных плейсхолдеров в тексте.
        Возвращает от 0 до 1.
        """
        if not text:
            return 0.0
        
        # Находим все FORMULA плейсхолдеры
        formulas = re.findall(r'\[\[FORMULA_[^\]]+\]\]', text)
        formula_chars = sum(len(f) for f in formulas)
        
        # Общая длина текста
        total_chars = len(text)
        
        if total_chars == 0:
            return 0.0
        
        return formula_chars / total_chars
    
    def _check_mandatory_criteria(self, chunk: Dict) -> Tuple[bool, str]:
        """
        Проверяет обязательные критерии для чанка.
        Возвращает (passed, reason).
        """
        text = chunk.get('processed_text', '')
        metadata = chunk.get('metadata', {})
        
        # 1. Проверка word_count
        word_count = metadata.get('word_count', 0)
        if word_count < self.REJECT_CRITERIA['min_word_count']:
            return False, f"word_count={word_count} < {self.REJECT_CRITERIA['min_word_count']}"
        
        # 2. Проверка ключевых терминов
        key_terms = metadata.get('key_terms', [])
        if len(key_terms) < self.REJECT_CRITERIA['min_key_terms']:
            return False, f"key_terms пуст"
        
        # 3. Проверка формул (если требуется)
        if self.REJECT_CRITERIA['require_formulas']:
            formula_count = metadata.get('formula_count', 0)
            if formula_count < self.REJECT_CRITERIA['min_formula_count']:
                return False, f"formula_count={formula_count} < {self.REJECT_CRITERIA['min_formula_count']}"
        
        # 4. Проверка на мусор (слишком много плейсхолдеров)
        placeholder_ratio = self._calculate_placeholder_ratio(text)
        if placeholder_ratio > self.REJECT_CRITERIA['max_placeholder_ratio']:
            return False, f"placeholder_ratio={placeholder_ratio:.2f} > {self.REJECT_CRITERIA['max_placeholder_ratio']}"
        
        # 5. Проверка, что текст не состоит только из плейсхолдеров
        clean_text = re.sub(r'\[\[FORMULA_[^\]]+\]\]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if len(clean_text) < 20:  # Минимум 20 символов обычного текста
            return False, f"Осмысленного текста < 20 символов"
        
        return True, "OK"
    
    def _calculate_informativeness_score(self, chunk: Dict) -> float:
        """
        Вычисляет score информативности для чанка.
        Чем выше score, тем ценнее чанк.
        """
        metadata = chunk.get('metadata', {})
        text = chunk.get('processed_text', '')
        
        score = 0.0
        
        # 1. Формулы (каждая формула = +3.0)
        formula_count = metadata.get('formula_count', 0)
        score += formula_count * self.SCORE_WEIGHTS['formula_count']
        
        # 2. Ключевые термины (каждый термин = +2.0)
        key_terms = metadata.get('key_terms', [])
        score += len(key_terms) * self.SCORE_WEIGHTS['key_terms_count']
        
        # 3. Оптимальный размер (20-300 слов)
        word_count = metadata.get('word_count', 0)
        if 20 <= word_count <= 300:
            score += self.SCORE_WEIGHTS['word_count_optimal']
        elif 10 <= word_count <= 500:
            score += self.SCORE_WEIGHTS['word_count_optimal'] * 0.5
        
        # 4. Лексическое разнообразие > 0.4
        lexical_diversity = metadata.get('lexical_diversity', 0)
        if lexical_diversity > 0.4:
            score += self.SCORE_WEIGHTS['lexical_diversity']
        elif lexical_diversity > 0.3:
            score += self.SCORE_WEIGHTS['lexical_diversity'] * 0.5
        
        # 5. Определена тема
        main_topic = metadata.get('main_topic', '')
        if main_topic and main_topic != 'неизвестно' and main_topic != 'unknown':
            score += self.SCORE_WEIGHTS['has_topic']
        
        # 6. Наличие определений (если поле есть)
        has_definitions = metadata.get('has_definitions', False)
        if has_definitions:
            score += self.SCORE_WEIGHTS['has_definitions']
        
        # 7. Наличие примеров (если поле есть)
        has_examples = metadata.get('has_examples', False)
        if has_examples:
            score += self.SCORE_WEIGHTS['has_examples']
        
        # 8. Оптимальное количество предложений
        sentence_count = metadata.get('sentence_count', 0)
        if 3 <= sentence_count <= 15:
            score += self.SCORE_WEIGHTS['sentence_count_optimal']
        
        # 9. Дополнительные поля (если есть)
        topic_relevance = metadata.get('topic_relevance', 0)
        if topic_relevance > 0.5:
            score += 3.0
        
        section_type = metadata.get('section_type', '')
        if section_type and section_type not in ['введение', 'заключение', 'introduction', 'conclusion']:
            score += 1.5
        
        return score
    
    def select_top_chunks(self, 
                          max_tokens: int = None,
                          coverage_pct: int = 80,
                          strict_mode: bool = True) -> Tuple[List[Dict], Dict]:
        """
        Отбирает лучшие чанки по информативности с учётом лимита токенов.
        
        Args:
            max_tokens: Максимальное количество токенов (None = авто)
            coverage_pct: Процент заполнения контекстного окна
            strict_mode: Строгий режим (отклонять некачественные чанки)
        
        Returns:
            (selected_chunks, selection_info)
        """
        print(f"\n{'='*60}")
        print(f"🎯 ОТБОР ЧАНКОВ ПО ИНФОРМАТИВНОСТИ")
        print(f"{'='*60}")
        
        # === ШАГ 1: Фильтрация по обязательным критериям ===
        print(f"\n🔍 ШАГ 1: Фильтрация чанков...")
        
        passed_chunks = []
        rejected_chunks = []
        
        for i, chunk in enumerate(self.chunks):
            passed, reason = self._check_mandatory_criteria(chunk)
            
            if passed:
                passed_chunks.append({
                    'chunk': chunk,
                    'index': i,
                    'reason': reason
                })
            else:
                rejected_chunks.append({
                    'chunk': chunk,
                    'index': i,
                    'reason': reason
                })
        
        print(f"  • Прошло фильтрацию: {len(passed_chunks)} чанков")
        print(f"  • Отклонено: {len(rejected_chunks)} чанков")
        
        if rejected_chunks:
            # Показываем причины отклонения
            reasons = {}
            for r in rejected_chunks:
                reason = r['reason'].split(':')[0] if ':' in r['reason'] else r['reason']
                reasons[reason] = reasons.get(reason, 0) + 1
            
            print(f"  • Причины отклонения:")
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                print(f"    - {reason}: {count} чанков")
        
        if not passed_chunks:
            print(f"  ⚠ Все чанки отклонены! Смягчаю критерии...")
            # В мягком режиме берём все чанки
            passed_chunks = [{'chunk': c, 'index': i, 'reason': 'soft_mode'} 
                           for i, c in enumerate(self.chunks)]
        
        # === ШАГ 2: Scoring ===
        print(f"\n📊 ШАГ 2: Оценка информативности...")
        
        for item in passed_chunks:
            item['score'] = self._calculate_informativeness_score(item['chunk'])
            item['tokens'] = estimate_tokens_gigachat(
                item['chunk'].get('processed_text', '')
            )
        
        # Сортируем по убыванию score
        passed_chunks.sort(key=lambda x: x['score'], reverse=True)
        
        # Статистика scores
        scores = [item['score'] for item in passed_chunks]
        if scores:
            print(f"  • Score: мин={min(scores):.1f}, макс={max(scores):.1f}, "
                  f"сред={sum(scores)/len(scores):.1f}")
        
        # Показываем топ-5 по информативности
        print(f"  • Топ-5 чанков по score:")
        for i, item in enumerate(passed_chunks[:5], 1):
            meta = item['chunk'].get('metadata', {})
            print(f"    {i}. Score={item['score']:.1f} | "
                  f"Слов: {meta.get('word_count', 0)} | "
                  f"Формул: {meta.get('formula_count', 0)} | "
                  f"Терминов: {len(meta.get('key_terms', []))}")
        
        # === ШАГ 3: Расчет лимита токенов ===
        print(f"\n📐 ШАГ 3: Расчет лимита токенов...")
        
        if max_tokens is None:
            # Автоматический расчет
            MAX_CONTEXT = MODEL_CONFIG["context_window"]  # 130 048
            RESPONSE_RESERVE = MODEL_CONFIG["max_output_tokens"]  # 4 096
            PROMPT_OVERHEAD = TOTAL_PROMPT_OVERHEAD + 2_000  # ~5 400
            SAFETY_MARGIN = 0.90
            
            max_tokens = int(
                (MAX_CONTEXT - RESPONSE_RESERVE - PROMPT_OVERHEAD) * SAFETY_MARGIN
            )
        
        print(f"  • Доступно токенов: {max_tokens:,}")
        print(f"  • Целевое заполнение: {coverage_pct}%")
        
        target_tokens = int(max_tokens * coverage_pct / 100)
        print(f"  • Целевой объём: {target_tokens:,} токенов")
        
        # === ШАГ 4: Отбор с контролем токенов ===
        print(f"\n✅ ШАГ 4: Отбор лучших чанков...")
        
        selected = []
        selected_tokens = 0
        
        for item in passed_chunks:
            if selected_tokens + item['tokens'] > target_tokens:
                # Пробуем добавить частично, если осталось место
                remaining = target_tokens - selected_tokens
                if remaining > item['tokens'] * 0.5:  # Если влезает >50% чанка
                    selected.append(item['chunk'])
                    selected_tokens += item['tokens']
                break
            
            selected.append(item['chunk'])
            selected_tokens += item['tokens']
        
        # === ШАГ 5: Статистика ===
        # Собираем метрики покрытия
        total_formulas = sum(
            c['chunk'].get('metadata', {}).get('formula_count', 0) 
            for c in passed_chunks
        )
        covered_formulas = sum(
            c.get('metadata', {}).get('formula_count', 0) 
            for c in selected
        )
        
        all_terms = set()
        for c in passed_chunks:
            all_terms.update(c['chunk'].get('metadata', {}).get('key_terms', []))
        
        covered_terms = set()
        for c in selected:
            covered_terms.update(c.get('metadata', {}).get('key_terms', []))
        
        selection_info = {
            "total_chunks_in_file": len(self.chunks),
            "passed_filter": len(passed_chunks),
            "rejected": len(rejected_chunks),
            "selected_count": len(selected),
            "selected_tokens": selected_tokens,
            "target_tokens": target_tokens,
            "token_usage_pct": round(selected_tokens / max_tokens * 100, 1),
            "total_formulas": total_formulas,
            "formulas_covered": covered_formulas,
            "formulas_coverage_pct": round(covered_formulas / total_formulas * 100, 1) if total_formulas else 0,
            "total_unique_terms": len(all_terms),
            "terms_covered": len(covered_terms),
            "terms_coverage_pct": round(len(covered_terms) / len(all_terms) * 100, 1) if all_terms else 0,
            "avg_score": sum(item['score'] for item in passed_chunks[:len(selected)]) / len(selected) if selected else 0,
            "strategy": "top_informativeness"
        }
        
        print(f"\n{'='*60}")
        print(f"📊 РЕЗУЛЬТАТ ОТБОРА")
        print(f"{'='*60}")
        print(f"  • Отобрано: {len(selected)} чанков")
        print(f"  • Токенов: {selected_tokens:,} из {target_tokens:,} ({selection_info['token_usage_pct']}%)")
        print(f"  • Средний score: {selection_info['avg_score']:.1f}")
        print(f"  • Покрытие формул: {selection_info['formulas_coverage_pct']}%")
        print(f"  • Покрытие терминов: {selection_info['terms_coverage_pct']}%")
        
        return selected, selection_info
    
    def get_chunk_texts(self, selected_chunks: List[Dict]) -> List[str]:
        """Извлекает тексты из отобранных чанков"""
        return [c.get('processed_text', '') for c in selected_chunks if c.get('processed_text')]
    
    def print_top_chunks(self, n: int = 5):
        """Выводит топ-N чанков с деталями"""
        chunks_scored = []
        for chunk in self.chunks:
            metadata = chunk.get('metadata', {})
            passed, _ = self._check_mandatory_criteria(chunk)
            score = self._calculate_informativeness_score(chunk) if passed else 0
            
            chunks_scored.append({
                'chunk': chunk,
                'score': score,
                'passed': passed,
                'word_count': metadata.get('word_count', 0),
                'formula_count': metadata.get('formula_count', 0),
                'key_terms': metadata.get('key_terms', []),
                'main_topic': metadata.get('main_topic', 'N/A'),
                'lexical_diversity': metadata.get('lexical_diversity', 0),
                'has_definitions': metadata.get('has_definitions', False),
                'has_examples': metadata.get('has_examples', False)
            })
        
        chunks_scored.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"\n🏆 ТОП-{n} САМЫХ ИНФОРМАТИВНЫХ ЧАНКОВ:")
        print(f"{'='*80}")
        
        for i, item in enumerate(chunks_scored[:n], 1):
            print(f"\n#{i} | Score: {item['score']:.1f} | {'✅' if item['passed'] else '❌'}")
            print(f"  Слов: {item['word_count']} | Формул: {item['formula_count']} | "
                  f"Терминов: {len(item['key_terms'])}")
            print(f"  Тема: {item['main_topic']} | Лекс.разн: {item['lexical_diversity']:.2f}")
            print(f"  Определения: {item['has_definitions']} | Примеры: {item['has_examples']}")
            print(f"  Текст: {item['chunk'].get('processed_text', '')[:150]}...")


def main():
    """Демонстрация работы"""
    
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    if not Path(json_file).exists():
        print(f"❌ Файл не найден: {json_file}")
        return
    
    # Создаем селектор
    selector = SmartChunkSelector(json_file)
    
    # Показываем топ-10 чанков
    selector.print_top_chunks(10)
    
    # Отбираем лучшие чанки
    selected, info = selector.select_top_chunks(
        coverage_pct=80,
        strict_mode=True
    )
    
    # Сохраняем результат
    output_path = f"top_chunks_result_{Path(json_file).stem}.json"
    
    result = {
        "selection_info": info,
        "selected_count": len(selected),
        "chunks": selected
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n💾 Результат сохранён: {output_path}")


if __name__ == "__main__":
    main()
