"""
chunk_range_calculator.py
Расчет минимального и максимального количества чанков для отправки в LLM.

Характеристики модели:
- Контекстное окно: 128 000 токенов
- Максимальная длина ответа: 32 768 токенов
- Поддерживаемые форматы: JSON

"""

import json
import numpy as np
from typing import Tuple, List, Dict, Optional
from pathlib import Path

MODEL_CONFIG = {
    "context_window": 128_000,      # контекстное окно модели (токены)
    "max_output_tokens": 32_768,    # максимальная длина ответа (токены)
    "token_factor": 1.8,            # для русского текста: символы / 1.8 = токены
    "safety_margin": 0.85,          # используем 85% окна для безопасности
}

PROMPT_OVERHEAD = {
    "system_prompt": 800,           # системная инструкция
    "user_instructions": 500,       # инструкции пользователя (параметры теста)
    "json_structure": 300,          # описание формата JSON
    "examples": 600,                # few-shot примеры (если используются)
    "formatting": 200,              # форматирование, переносы строк
    "reserve": 1_000,               # резерв на непредвиденные расходы
}

# Итого overhead на промпт (без чанков)
TOTAL_PROMPT_OVERHEAD = sum(PROMPT_OVERHEAD.values())  # = 3400 токенов

def estimate_tokens(text: str, method: str = "russian") -> int:
    """
    Оценка количества токенов в тексте.
    """
    if not text:
        return 0
    
    if method == "russian":
        # Для русского текста: 1 токен ≈ 1.5-2 символа
        # Берем коэффициент 1.8 для безопасности
        return max(1, int(len(text) / MODEL_CONFIG["token_factor"]))
    else:
        # Грубая оценка: 1 токен ≈ 4 символа
        return max(1, len(text) // 4)

def analyze_chunks_detailed(chunks: List[Dict]) -> Dict:
    """
    Детальный анализ чанков для расчета диапазона.
    """
    if not chunks:
        return {"error": "Нет чанков для анализа"}
    
    # Сбор метрик по каждому чанку
    chunk_data = []
    total_chars = 0
    total_tokens = 0
    
    for idx, chunk in enumerate(chunks):
        text = chunk.get("processed_text", "")
        chars = len(text)
        tokens = estimate_tokens(text)
        
        metadata = chunk.get("metadata", {})
        formula_count = metadata.get("formula_count", 0)
        key_terms = metadata.get("key_terms", [])
        word_count = metadata.get("word_count", 0)
        has_formulas = metadata.get("has_formulas", False)
        lexical_diversity = metadata.get("lexical_diversity", 0)
        
        total_chars += chars
        total_tokens += tokens
        
        chunk_data.append({
            "id": chunk.get("id", f"chunk_{idx}"),
            "sequence": chunk.get("sequence", idx),
            "chars": chars,
            "tokens": tokens,
            "formula_count": formula_count,
            "key_terms_count": len(key_terms),
            "has_formulas": has_formulas,
            "word_count": word_count,
            "lexical_diversity": lexical_diversity,
            "text_preview": text[:100] + "..." if len(text) > 100 else text
        })
    
    # Статистика
    tokens_list = [d["tokens"] for d in chunk_data]
    chars_list = [d["chars"] for d in chunk_data]
    
    # Сортируем по информативности для MIN расчета
    chunk_data_sorted = sorted(chunk_data, 
                               key=lambda x: (x["formula_count"] + x["key_terms_count"]), 
                               reverse=True)
    
    return {
        "total_chunks": len(chunks),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "avg_chunk_tokens": int(np.mean(tokens_list)) if tokens_list else 0,
        "std_chunk_tokens": int(np.std(tokens_list)) if tokens_list else 0,
        "min_chunk_tokens": min(tokens_list) if tokens_list else 0,
        "max_chunk_tokens": max(tokens_list) if tokens_list else 0,
        "avg_chunk_chars": int(np.mean(chars_list)) if chars_list else 0,
        "chunks_with_formulas": sum(1 for d in chunk_data if d["has_formulas"]),
        "total_formulas": sum(d["formula_count"] for d in chunk_data),
        "total_key_terms": sum(d["key_terms_count"] for d in chunk_data),
        "chunk_data": chunk_data,
        "chunk_data_sorted": chunk_data_sorted
    }


def calculate_max_chunks(stats: Dict,
                         model_config: Dict = None,
                         prompt_overhead: int = None,
                         reserve_for_response: int = None) -> Tuple[int, Dict]:
    """
    Расчет максимального количества чанков с учетом контекстного окна.
    
    Формула:
        max_chunks = (context_window - prompt_overhead - response_reserve) * safety / avg_chunk_size
    Returns:
        (max_chunks, dict_with_details)
    """
    if "error" in stats:
        return 5, {"error": stats["error"]}
    
    config = model_config or MODEL_CONFIG
    overhead = prompt_overhead or TOTAL_PROMPT_OVERHEAD
    response_reserve = reserve_for_response or config["max_output_tokens"]
    
    context_window = config["context_window"]
    safety_margin = config["safety_margin"]
    avg_chunk_tokens = stats["avg_chunk_tokens"]
    
    # Расчет доступного места для чанков
    available_for_chunks = int((context_window - overhead - response_reserve) * safety_margin)
    
    # Расчет максимального количества чанков
    if avg_chunk_tokens > 0:
        max_by_tokens = max(1, int(available_for_chunks / avg_chunk_tokens))
    else:
        max_by_tokens = 1
    
    # Дополнительные ограничения
    max_chunks = min(max_by_tokens, stats["total_chunks"])
    max_chunks = max(max_chunks, 1)  # минимум 1
    
    details = {
        "context_window": context_window,
        "prompt_overhead": overhead,
        "response_reserve": response_reserve,
        "safety_margin": safety_margin,
        "available_for_chunks": available_for_chunks,
        "avg_chunk_tokens": avg_chunk_tokens,
        "max_by_tokens": max_by_tokens,
        "max_chunks": max_chunks,
        "estimated_tokens_used": max_chunks * avg_chunk_tokens + overhead + response_reserve,
        "percentage_of_context": round((max_chunks * avg_chunk_tokens + overhead + response_reserve) / context_window * 100, 1)
    }
    
    return max_chunks, details


def calculate_min_chunks(stats: Dict,
                         min_questions: int = 5,
                         min_formulas_per_question: float = 0.5,
                         min_unique_terms: int = 5,
                         min_chunks_absolute: int = 2) -> Tuple[int, Dict]:
    """
    Расчет минимального количества чанков на основе покрытия материала.   
    Returns:
        (min_chunks, dict_with_details)
    """
    if "error" in stats:
        return min_chunks_absolute, {"error": stats["error"]}
    
    needed_formulas = min_questions * min_formulas_per_question
    needed_terms = min_unique_terms
    
    chunk_data_sorted = stats.get("chunk_data_sorted", [])
    
    formulas_covered = 0
    terms_covered = set()
    chunks_needed = 0
    
    for chunk in chunk_data_sorted:
        chunks_needed += 1
        formulas_covered += chunk["formula_count"]
        terms_covered.update([chunk.get("text_preview", "")[:50]])  # упрощенно
        
        if formulas_covered >= needed_formulas and len(terms_covered) >= needed_terms:
            break
    
    # Ограничения
    min_chunks = max(chunks_needed, min_chunks_absolute)
    min_chunks = min(min_chunks, stats["total_chunks"] // 2)
    
    details = {
        "min_questions": min_questions,
        "min_formulas_per_question": min_formulas_per_question,
        "needed_formulas": needed_formulas,
        "needed_terms": needed_terms,
        "formulas_covered": formulas_covered,
        "terms_covered": len(terms_covered),
        "chunks_needed_by_coverage": chunks_needed,
        "min_chunks": min_chunks
    }
    
    return min_chunks, details


def get_chunk_range(json_path: str,
                    model_context_window: int = 128_000,
                    max_output_tokens: int = 32_768,
                    verbose: bool = True) -> Tuple[int, int]:
    """
    Главная функция: возвращает (MAX, MIN) количество чанков.
    
    Returns:
        Кортеж (max_chunks, min_chunks)
        Пример: (23, 4) - можно отправить все 23 чанка
    """
    # Обновляем конфигурацию
    config = MODEL_CONFIG.copy()
    config["context_window"] = model_context_window
    config["max_output_tokens"] = max_output_tokens
    
    # Загрузка файла
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {json_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data.get("chunks", [])
    
    if not chunks:
        raise ValueError("В файле нет чанков (поле 'chunks' пустое)")
    
    # Анализ
    stats = analyze_chunks_detailed(chunks)
    
    # Расчет MAX
    max_chunks, max_details = calculate_max_chunks(stats, config)
    
    # Расчет MIN
    min_chunks, min_details = calculate_min_chunks(stats)
    
    # Корректировка: MIN не может быть больше MAX
    if min_chunks > max_chunks:
        min_chunks = max(2, max_chunks // 2)
    
    # Вывод информации
    if verbose:
        print("📊 РАСЧЕТ ДИАПАЗОНА ЧАНКОВ С УЧЕТОМ КОНТЕКСТНОГО ОКНА")
        
        print(f" Контекстное окно: {config['context_window']:,} токенов")
        print(f" Макс. длина ответа: {config['max_output_tokens']:,} токенов")
        print(f" Коэффициент токенизации: 1 символ ≈ {1/config['token_factor']:.2f} токена")
        
        print("\n РАСХОД ТОКЕНОВ НА ПРОМПТ (OVERHEAD):")
        for key, value in PROMPT_OVERHEAD.items():
            print(f"   • {key}: {value:,} токенов")
        print(f"   • ИТОГО overhead: {TOTAL_PROMPT_OVERHEAD:,} токенов")
        
        print("\n СТАТИСТИКА ЧАНКОВ:")
        print(f" Всего чанков: {stats['total_chunks']}")
        print(f" Общий объем: {stats['total_tokens']:,} токенов")
        print(f" Средний размер: {stats['avg_chunk_tokens']} токенов")
        print(f" Разброс: {stats['min_chunk_tokens']} - {stats['max_chunk_tokens']} токенов")
        print(f" Чанков с формулами: {stats['chunks_with_formulas']}/{stats['total_chunks']}")
        print(f" Всего формул: {stats['total_formulas']}")
        
        print(" ИТОГОВЫЙ ДИАПАЗОН:")
        print(f" MAX (максимум) = {max_chunks} чанков")
        print(f" MIN (минимум)  = {min_chunks} чанков")
        print(f" Рекомендуемое  = {(max_chunks + min_chunks) // 2} чанков")
        
        # Проверка: можно ли отправить все чанки?
        if stats['total_tokens'] + TOTAL_PROMPT_OVERHEAD + config['max_output_tokens'] <= config['context_window']:
            print(f"\n Все {stats['total_chunks']} Чанки влезают в котекст!")
            print(f"   Можете использовать стратегию S_all (все чанки)")
        else:
            print(f"\n НЕ все чанков влезают. Используйте стратегию фильтрации.")
        
        print("="*70)
    
    return max_chunks, min_chunks
