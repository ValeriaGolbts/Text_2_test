#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для связи pipeline и generator
"""
import json
import sys
from pathlib import Path

# Простой импорт из той же папки
try:
    from gigachat_client import GigaChatClient
except ImportError:
    # Если нет файла gigachat_client.py, создаем заглушку
    class GigaChatClient:
        def generate_test(self, text_chunks, subject="", num_questions=10):
            print("🔵 Эмуляция GigaChat (файл клиента не найден)")
            return {
                "test_title": f"Тест по {subject}",
                "questions": [
                    {
                        "id": i,
                        "question": f"Вопрос {i}",
                        "options": ["А", "Б", "В", "Г"],
                        "correct_answer": "А"
                    } for i in range(1, num_questions + 1)
                ]
            }

def main():
    print("🔄 pipeline → generator")
    print("=" * 50)
    
    # Путь к файлу от коллеги
    json_path = Path("C:/Users/валерия/Projects/Text_2_test/output.json")
    
    if not json_path.exists():
        print(f"❌ Файл не найден: {json_path}")
        return
    
    # Читаем JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"✅ Загружен файл: {json_path}")
    
    # Извлекаем тексты
    texts = []
    for chunk in data.get('chunks', []):
        text = chunk.get('processed_text', '')
        if text:
            texts.append(text)
    
    print(f"📝 Извлечено {len(texts)} текстовых блоков")
    
    # Отправляем в GigaChat
    print("🤖 Отправка в GigaChat...")
    client = GigaChatClient()
    result = client.generate_test(text_chunks=texts)
    
    # Сохраняем результат
    output_file = Path("test_result.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Результат сохранен в: {output_file}")

if __name__ == "__main__":
    main()
