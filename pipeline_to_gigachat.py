# src/integration/pipeline_to_gigachat.py
"""
Интеграция pipeline (структурированный JSON) с GigaChat генератором
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.generator.gigachat_client import GigaChatClient
from src.generator.prompt_templates import TestPromptTemplates


class PipelineProcessor:
    """Обработчик выходных данных от pipeline модуля"""
    
    def __init__(self, json_file_path: str):
        """
        Инициализация с путем к JSON файлу от pipeline
        
        Args:
            json_file_path: путь к output.json
        """
        self.file_path = Path(json_file_path)
        self.data = self._load_json()
        
    def _load_json(self) -> Dict[str, Any]:
        """Загружает JSON файл"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ Загружен файл: {self.file_path}")
            return data
        except Exception as e:
            print(f"❌ Ошибка загрузки: {e}")
            return {}
    
    def print_summary(self):
        """Выводит краткую информацию о данных"""
        if not self.data:
            return
        
        print("\n📊 Статистика от pipeline:")
        print(f"  📄 Файл: {self.data.get('source_file', 'N/A')}")
        print(f"  🆔 Process ID: {self.data.get('process_id', 'N/A')}")
        print(f"  ⏱️  Обработано: {self.data.get('processed_at', 'N/A')}")
        
        stats = self.data.get('statistics', {})
        print(f"\n  📈 Статистика обработки:")
        print(f"    • Всего чанков: {stats.get('total_chunks', 0)}")
        print(f"    • Всего формул: {stats.get('total_formulas', 0)}")
        print(f"    • Время обработки: {stats.get('processing_time_seconds', 0)} сек")
        
        norm_stats = stats.get('normalization_stats', {})
        print(f"\n  ✂️  Нормализация текста:")
        print(f"    • Было символов: {norm_stats.get('original_length', 0)}")
        print(f"    • Стало символов: {norm_stats.get('normalized_length', 0)}")
    
    def extract_processed_texts(self) -> List[str]:
        """
        Извлекает processed_text из всех чанков
        
        Returns:
            Список обработанных текстов
        """
        chunks = self.data.get('chunks', [])
        if not chunks:
            print("❌ Нет чанков в данных")
            return []
        
        processed_texts = []
        for chunk in chunks:
            text = chunk.get('processed_text', '')
            if text:  # добавляем только непустые
                processed_texts.append(text)
        
        print(f"\n📝 Извлечено {len(processed_texts)} текстовых блоков")
        
        # Покажем пример первого блока
        if processed_texts:
            print("\n📄 Пример первого блока:")
            print(f"   {processed_texts[0][:200]}...")
            
            # Покажем метаданные первого чанка
            first_chunk = chunks[0]
            metadata = first_chunk.get('metadata', {})
            print(f"\n🏷️  Метаданные первого блока:")
            print(f"   • Тема: {metadata.get('main_topic', 'N/A')}")
            print(f"   • Слов: {metadata.get('word_count', 0)}")
            print(f"   • Ключевые термины: {metadata.get('key_terms', [])[:5]}")
        
        return processed_texts
    
    def extract_topics(self) -> List[str]:
        """
        Извлекает все ключевые темы из чанков
        
        Returns:
            Список уникальных тем
        """
        chunks = self.data.get('chunks', [])
        all_topics = []
        
        for chunk in chunks:
            metadata = chunk.get('metadata', {})
            topics = metadata.get('key_terms', [])
            all_topics.extend(topics)
        
        # Уникальные темы
        unique_topics = list(set(all_topics))
        print(f"\n🎯 Найдено {len(unique_topics)} уникальных тем")
        return unique_topics
    
    def get_main_topic(self) -> str:
        """Определяет основную тему из метаданных"""
        chunks = self.data.get('chunks', [])
        topics_count = {}
        
        for chunk in chunks:
            metadata = chunk.get('metadata', {})
            topic = metadata.get('main_topic', 'unknown')
            topics_count[topic] = topics_count.get(topic, 0) + 1
        
        if topics_count:
            main_topic = max(topics_count, key=topics_count.get)
            return main_topic
        return "учебный материал"
    
    def get_difficulty_from_stats(self) -> str:
        """
        Определяет сложность материала на основе статистики
        """
        stats = self.data.get('statistics', {})
        formula_count = stats.get('total_formulas', 0)
        
        if formula_count > 200:
            return "hard"
        elif formula_count > 100:
            return "medium"
        else:
            return "easy"


class PipelineToGenerator:
    """Основной класс для интеграции pipeline и generator"""
    
    def __init__(self, json_file_path: str):
        self.processor = PipelineProcessor(json_file_path)
        self.generator = GigaChatClient()
        self.prompts = TestPromptTemplates()
        
    def run(self, num_questions: int = 10) -> Dict:
        """
        Запускает полный процесс: pipeline → GigaChat → результат
        
        Args:
            num_questions: количество вопросов в тесте
            
        Returns:
            Словарь с результатами
        """
        print("\n🚀 Запуск интеграции pipeline → generator")
        print("=" * 60)
        
        # 1. Показываем информацию от pipeline
        self.processor.print_summary()
        
        # 2. Извлекаем тексты
        texts = self.processor.extract_processed_texts()
        if not texts:
            raise ValueError("Нет текстов для обработки")
        
        # 3. Определяем тему и сложность
        subject = self.processor.get_main_topic()
        difficulty = self.processor.get_difficulty_from_stats()
        topics = self.processor.extract_topics()
        
        print(f"\n🎯 Определенные параметры:")
        print(f"   • Тема: {subject}")
        print(f"   • Сложность: {difficulty}")
        print(f"   • Ключевые темы: {topics[:10]}")
        
        # 4. Генерируем тест
        print(f"\n🤖 Отправка в GigaChat ({num_questions} вопросов)...")
        try:
            test_result = self.generator.generate_test(
                text_chunks=texts,
                subject=subject,
                num_questions=num_questions,
                difficulty=difficulty
            )
            
            # 5. Добавляем метаданные от pipeline
            test_result['pipeline_metadata'] = {
                'source_file': self.processor.data.get('source_file'),
                'process_id': self.processor.data.get('process_id'),
                'processed_at': self.processor.data.get('processed_at'),
                'statistics': self.processor.data.get('statistics'),
                'topics_used': topics[:20]  # сохраняем топ-20 тем
            }
            
            # 6. Сохраняем результат
            self._save_result(test_result)
            
            return test_result
            
        except Exception as e:
            print(f"❌ Ошибка при генерации: {e}")
            raise
    
    def _save_result(self, result: Dict):
        """Сохраняет результат в JSON файл"""
        # Создаем имя файла с датой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_file = self.processor.data.get('source_file', 'unknown')
        source_name = Path(source_file).stem
        
        output_dir = Path(__file__).parent.parent.parent / "generated_tests"
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f"test_{source_name}_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результат сохранен в: {output_file}")
        
        # Показываем статистику
        questions = result.get('questions', [])
        print(f"\n📊 Итоговая статистика:")
        print(f"   • Всего вопросов: {len(questions)}")
        if questions:
            print(f"   • Первый вопрос: {questions[0].get('question', '')[:100]}...")


def main():
    """Основная функция запуска"""
    
    # Путь к файлу от pipeline
    possible_paths = [
        Path(__file__).parent.parent.parent / "output.json",
        Path(__file__).parent.parent.parent / "data" / "output.json",
        Path("C:/Users/валерия/Projects/Text_2_test/output.json"),
        Path("C:/Users/валерия/Projects/Text_2_test/data/output.json"),
    ]
    
    json_file = None
    for path in possible_paths:
        if path.exists():
            json_file = path
            break
    
    if not json_file:
        print("❌ Файл output.json не найден!")
        print("🔍 Искал в:")
        for path in possible_paths:
            print(f"   • {path}")
        return
    
    try:
        # Создаем интегратор
        integrator = PipelineToGenerator(str(json_file))
        
        # Запускаем с 10 вопросами (можно изменить)
        result = integrator.run(num_questions=10)
        
        print("\n✅ Интеграция успешно завершена!")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    main()
