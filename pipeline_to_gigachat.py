# process_json_with_gigachat.py
"""
Обработка JSON файла от pipeline через GigaChat B2B клиент
"""
import json
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from api_client_b2b import GigaChatB2BClient
from config import config
#from response_parser import TestParser

class PipelineJSONProcessor:
    """Обработчик JSON файлов от pipeline с отправкой в GigaChat"""
    
    def __init__(self):
        self.client = GigaChatB2BClient()
        #self.parser = TestParser()
        print(f"✅ Инициализирован B2B клиент для обработки JSON")
    
    def load_pipeline_json(self, json_path: str) -> Dict[str, Any]:
        """Загружает JSON файл от pipeline"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ Загружен JSON: {json_path}")
            return data
        except Exception as e:
            print(f"❌ Ошибка загрузки JSON: {e}")
            return {}
    
    def extract_text_from_chunks(self, pipeline_data: Dict[str, Any]) -> List[str]:
        """Извлекает текст из чанков"""
        texts = []
        chunks = pipeline_data.get('chunks', [])
        
        for chunk in chunks:
            text = chunk.get('processed_text', '')
            if text:
                texts.append(text)
        
        print(f"📝 Извлечено {len(texts)} текстовых блоков")
        
        # Показываем пример
        if texts:
            print(f"\n📄 Пример первого блока:")
            print(f"   {texts[0][:200]}...")
        
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
    
    def create_prompt(self, texts: List[str], num_questions: int = 10) -> str:
        """Создает промпт на основе текстов из pipeline"""
        
        # Объединяем тексты (берем первые 3-4 чанка для контекста)
        context = "\n\n".join(texts[:4])
        
        prompt = f"""На основе предоставленного учебного материала создай тест из {num_questions} вопросов.

ИСХОДНЫЙ МАТЕРИАЛ:
{context}

ТРЕБОВАНИЯ К ТЕСТУ:
1. Все вопросы должны быть строго по содержанию материала
2. Каждый вопрос должен иметь 4 варианта ответа
3. Только один вариант ответа правильный
4. Вопросы должны проверять понимание ключевых концепций
5. Избегай тривиальных и очевидных вопросов
6. Включи вопросы разной сложности

ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без пояснений):
{{
    "test_title": "Название теста по теме материала",
    "subject": "Определенная тема",
    "difficulty": "medium",
    "questions": [
        {{
            "id": 1,
            "question": "Текст вопроса",
            "options": ["Вариант А", "Вариант Б", "Вариант В", "Вариант Г"],
            "correct_answer": "Вариант А",
            "explanation": "Краткое пояснение правильного ответа"
        }}
    ]
}}

ВАЖНО: Верни ТОЛЬКО JSON, без дополнительного текста."""
        
        return prompt
    
    async def process_pipeline_json(self, json_path: str, num_questions: int = 10) -> Dict[str, Any]:
        """Основной метод: загружает JSON, отправляет в GigaChat, возвращает тест"""
        
        print("\n" + "="*60)
        print("🚀 ЗАПУСК ОБРАБОТКИ JSON ОТ PIPELINE")
        print("="*60)
        
        # 1. Загружаем JSON
        pipeline_data = self.load_pipeline_json(json_path)
        if not pipeline_data:
            return {"error": "Не удалось загрузить JSON"}
        
        # 2. Извлекаем тексты
        texts = self.extract_text_from_chunks(pipeline_data)
        if not texts:
            return {"error": "Нет текстов для обработки"}
        
        # 3. Получаем метаданные
        metadata = self.get_metadata(pipeline_data)
        print(f"\n📊 Метаданные от pipeline:")
        print(f"  • Исходный файл: {metadata['source_file']}")
        print(f"  • Process ID: {metadata['process_id']}")
        print(f"  • Всего чанков: {metadata['total_chunks']}")
        
        # 4. Создаем промпт
        prompt = self.create_prompt(texts, num_questions)
        print(f"\n🤖 Отправка в GigaChat ({num_questions} вопросов)...")
        
        # 5. Отправляем в GigaChat
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = await self.client.send_request(
                messages=messages,
                max_tokens=3000,
                temperature=0.7
            )
            
            print(f"✅ Получен ответ от GigaChat")
            
            # 6. Извлекаем JSON из ответа
            content = response['choices'][0]['message']['content']
            
            # Пытаемся найти JSON в ответе
            import re
            json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            # Очищаем от лишнего
            json_str = json_str.strip()
            if json_str.startswith('```'):
                json_str = json_str.split('```')[1]
                if json_str.startswith('json'):
                    json_str = json_str[4:]
            
            # Парсим JSON
            try:
                test_result = json.loads(json_str)
            except:
                # Если не получилось, пробуем найти JSON в тексте
                import re
                json_pattern = r'\{.*\}'
                match = re.search(json_pattern, json_str, re.DOTALL)
                if match:
                    test_result = json.loads(match.group())
                else:
                    test_result = {"raw_response": content, "questions": []}
            
            # 7. Добавляем метаданные pipeline
            test_result['pipeline_metadata'] = metadata
            
            return test_result
            
        except Exception as e:
            print(f"❌ Ошибка при отправке в GigaChat: {e}")
            return {"error": str(e), "pipeline_metadata": metadata}
    
    def save_result(self, result: Dict[str, Any], output_path: str = None):
        """Сохраняет результат в JSON файл"""
        if not output_path:
            # Создаем имя файла с датой
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"test_result_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результат сохранен в: {output_path}")
        return output_path


async def main():
    """Основная функция"""
    
    # Путь к JSON файлу от pipeline (ИЗМЕНИТЕ НА ВАШ!)
    json_file = r"C:\Users\валерия\Projects\Text_2_test\output.json"
    
    # Проверяем существование файла
    if not Path(json_file).exists():
        print(f"❌ Файл не найден: {json_file}")
        
        # Ищем в текущей папке
        current_dir = Path(__file__).parent
        possible_files = list(current_dir.glob("*.json"))
        if possible_files:
            print(f"\n🔍 Найденные JSON файлы в текущей папке:")
            for f in possible_files:
                print(f"  • {f}")
            
            # Берем первый
            json_file = str(possible_files[0])
            print(f"\n📁 Использую: {json_file}")
        else:
            return
    
    # Создаем процессор
    processor = PipelineJSONProcessor()
    
    # Обрабатываем JSON
    result = await processor.process_pipeline_json(
        json_path=json_file,
        num_questions=10  # Количество вопросов
    )
    
    # Сохраняем результат
    if 'error' not in result:
        output_file = processor.save_result(result)
        
        # Показываем статистику
        print("\n" + "="*60)
        print("📊 РЕЗУЛЬТАТ ГЕНЕРАЦИИ ТЕСТА")
        print("="*60)
        print(f"📌 Название: {result.get('test_title', 'Не указано')}")
        print(f"📌 Тема: {result.get('subject', 'Не указана')}")
        print(f"📌 Сложность: {result.get('difficulty', 'Не указана')}")
        print(f"📌 Вопросов: {len(result.get('questions', []))}")
        
        if result.get('questions'):
            print("\n❓ ПЕРВЫЙ ВОПРОС:")
            q = result['questions'][0]
            print(f"  {q.get('question', '')}")
            print("  Варианты:")
            for i, opt in enumerate(q.get('options', []), 1):
                print(f"    {i}. {opt}")
            print(f"  ✅ Правильный ответ: {q.get('correct_answer', '')}")
    else:
        print(f"\n❌ Ошибка: {result['error']}")

if __name__ == "__main__":
    asyncio.run(main())
