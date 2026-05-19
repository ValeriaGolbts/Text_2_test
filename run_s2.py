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
