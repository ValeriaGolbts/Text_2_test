"""
chunk_range_calculator.py
Расчет минимального и максимального количества чанков для отправки в LLM.
Поддерживает точный подсчёт токенов через GigaChat API и реалистичную оценку.

Характеристики модели:
- Контекстное окно: 130 048 токенов (GigaChat Pro)
- Максимальная длина ответа: 4 096 токенов
- Поддерживаемые форматы: JSON
"""

import json
import re
import numpy as np
from typing import Tuple, List, Dict, Optional, Callable
from pathlib import Path

# Конфигурация GigaChat Pro
MODEL_CONFIG = {
    "context_window": 130_048,      # Реальный контекст GigaChat Pro
    "max_output_tokens": 4_096,     # Максимальная длина ответа
    "token_factor": 3.5,            # 1 токен ≈ 3.5 символов (по данным GigaChat)
    "safety_margin": 0.90,          # Используем 90% окна для безопасности
}

PROMPT_OVERHEAD = {
    "system_prompt": 800,           # Системная инструкция
    "user_instructions": 500,       # Инструкции пользователя
    "json_structure": 300,          # Описание формата JSON
    "examples": 600,                # Few-shot примеры
    "formatting": 200,              # Форматирование, переносы строк
    "reserve": 1_000,               # Резерв на непредвиденные расходы
}

TOTAL_PROMPT_OVERHEAD = sum(PROMPT_OVERHEAD.values())  # = 3 400 токенов


def estimate_tokens_gigachat(text: str) -> int:
    """
    Реалистичная оценка токенов для GigaChat.
    Учитывает, что формулы и спецсимволы занимают 1 токен = 1 символ,
    а обычный текст ~3.5 символов на токен.
    
    Основано на официальной документации GigaChat:
    "В среднем в одном токене 3–4 символа, включая пробелы, 
    знаки препинания и специальные символы."
    """
    if not text:
        return 0
    
    # Паттерны для формул и спецсимволов
    formula_pattern = r'\[\[FORMULA_[^\]]+\]\]'
    special_chars_pattern = r'[∆→⇒∑∫∂√∞≈≠≤≥𝜋𝛼𝛽𝛾𝜃𝜆𝜇𝜎𝜔𝜀𝜁𝜂𝜄𝜅𝜈𝜉𝜌𝜍𝜏𝜐𝜑𝜒𝜓︀\(\)\[\]\{\}\^]'
    
    # Находим формулы (они токенизируются посимвольно)
    formulas = re.findall(formula_pattern, text)
    formula_chars = sum(len(f) for f in formulas)
    
    # Находим спецсимволы (тоже посимвольно)
    special_chars = len(re.findall(special_chars_pattern, text))
    
    # Очищаем текст от формул и спецсимволов для оценки обычного текста
    clean_text = re.sub(formula_pattern, '', text)
    clean_text = re.sub(special_chars_pattern, '', clean_text)
    normal_chars = len(clean_text)
    
    # Формулы и спецсимволы: 1 токен = 1 символ
    # Обычный текст: 1 токен ≈ 3.5 символов
    formula_tokens = formula_chars
    special_tokens = special_chars
    normal_tokens = normal_chars / MODEL_CONFIG["token_factor"]
    
    total = int(formula_tokens + special_tokens + normal_tokens)
    return max(1, total) if text else 0


def estimate_tokens_accurate(texts: List[str], giga_client=None) -> List[int]:
    """
    Точный подсчёт токенов через GigaChat API.
    Если клиент недоступен — использует реалистичную оценку.
    
    Args:
        texts: Список текстов для подсчёта
        giga_client: Клиент GigaChat (опционально)
    
    Returns:
        Список количества токенов для каждого текста
    """
    if giga_client and hasattr(giga_client, 'tokens_count'):
        try:
            result = giga_client.tokens_count(
                input_=texts,
                model="GigaChat-Pro"
            )
            if isinstance(result, list) and len(result) == len(texts):
                return [int(r) for r in result]
        except Exception as e:
            print(f"  ⚠ Ошибка точного подсчёта через API: {e}")
    
    # Fallback: реалистичная оценка
    return [estimate_tokens_gigachat(text) for text in texts]


def analyze_chunks_detailed(chunks: List[Dict], 
                            token_counter: Callable = None,
                            giga_client=None) -> Dict:
    """
    Детальный анализ чанков с точным или реалистичным подсчётом токенов.
    
    Args:
        chunks: Список чанков
        token_counter: Функция подсчёта токенов (опционально)
        giga_client: Клиент GigaChat для точного подсчёта (опционально)
    """
    if not chunks:
        return {"error": "Нет чанков для анализа"}
    
    # Собираем тексты
    texts = [chunk.get("processed_text", "") for chunk in chunks]
    
    # Выбираем метод подсчёта токенов
    if token_counter:
        token_counts = [token_counter(text) for text in texts]
    elif giga_client:
        token_counts = estimate_tokens_accurate(texts, giga_client)
    else:
        token_counts = [estimate_tokens_gigachat(text) for text in texts]
    
    # Сбор метрик по каждому чанку
    chunk_data = []
    total_chars = 0
    total_tokens = 0
    
    for idx, (chunk, tokens) in enumerate(zip(chunks, token_counts)):
        text = chunk.get("processed_text", "")
        chars = len(text)
        
        metadata = chunk.get("metadata", {})
        formula_count = metadata.get("formula_count", 0)
        key_terms = metadata.get("key_terms", [])
        has_formulas = metadata.get("has_formulas", False)
        
        total_chars += chars
        total_tokens += tokens
        
        chunk_data.append({
            "id": chunk.get("id", f"chunk_{idx}"),
            "sequence": chunk.get("sequence", idx),
            "chars": chars,
            "tokens": tokens,  # Точное или реалистичное значение
            "formula_count": formula_count,
            "key_terms_count": len(key_terms),
            "has_formulas": has_formulas,
            "text_preview": text[:100] + "..." if len(text) > 100 else text
        })
    
    # Статистика
    tokens_list = [d["tokens"] for d in chunk_data]
    chars_list = [d["chars"] for d in chunk_data]
    
    # Сортируем по информативности
    chunk_data_sorted = sorted(
        chunk_data,
        key=lambda x: (x["formula_count"] + x["key_terms_count"]),
        reverse=True
    )
    
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
    Расчет максимального количества чанков с учётом контекстного окна.
    
    Формула:
        max_chunks = (context_window - overhead - response_reserve) * safety / avg_chunk_size
    
    Returns:
        (max_chunks, details_dict)
    """
    if "error" in stats:
        return 5, {"error": stats["error"]}
    
    config = model_config or MODEL_CONFIG
    overhead = prompt_overhead or TOTAL_PROMPT_OVERHEAD
    response_reserve = reserve_for_response or config["max_output_tokens"]
    
    context_window = config["context_window"]
    safety_margin = config["safety_margin"]
    avg_chunk_tokens = stats["avg_chunk_tokens"]
    
    # Доступное место для чанков
    available_for_chunks = int(
        (context_window - overhead - response_reserve) * safety_margin
    )
    
    # Максимум по токенам
    if avg_chunk_tokens > 0:
        max_by_tokens = max(1, int(available_for_chunks / avg_chunk_tokens))
    else:
        max_by_tokens = 1
    
    max_chunks = min(max_by_tokens, stats["total_chunks"])
    max_chunks = max(max_chunks, 1)
    
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
        "percentage_of_context": round(
            (max_chunks * avg_chunk_tokens + overhead + response_reserve) 
            / context_window * 100, 1
        )
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
        (min_chunks, details_dict)
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
        terms_covered.update([chunk.get("text_preview", "")[:50]])
        
        if formulas_covered >= needed_formulas and len(terms_covered) >= needed_terms:
            break
    
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
                    giga_client=None,
                    verbose: bool = True) -> Tuple[int, int]:
    """
    Главная функция: возвращает (MAX, MIN) количество чанков.
    
    Args:
        json_path: Путь к JSON файлу с чанками
        giga_client: Клиент GigaChat для точного подсчёта (опционально)
        verbose: Выводить ли детальную информацию
    
    Returns:
        Кортеж (max_chunks, min_chunks)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {json_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunks = data.get("chunks", [])
    
    if not chunks:
        raise ValueError("В файле нет чанков (поле 'chunks' пустое)")
    
    # Анализ с точным подсчётом
    stats = analyze_chunks_detailed(chunks, giga_client=giga_client)
    
    # Расчет MAX и MIN
    max_chunks, max_details = calculate_max_chunks(stats)
    min_chunks, min_details = calculate_min_chunks(stats)
    
    # Корректировка: MIN не может быть больше MAX
    if min_chunks > max_chunks:
        min_chunks = max(2, max_chunks // 2)
    
    if verbose:
        print(f"\n📊 РАСЧЕТ ДИАПАЗОНА ЧАНКОВ")
        print(f"  Контекстное окно: {MODEL_CONFIG['context_window']:,} токенов")
        print(f"  Средний чанк: {stats['avg_chunk_tokens']} токенов")
        print(f"  Всего чанков: {stats['total_chunks']}")
        print(f"  Общий объём: {stats['total_tokens']:,} токенов")
        print(f"  MAX (максимум): {max_chunks} | MIN (минимум): {min_chunks}")
    
    return max_chunks, min_chunks
