# Принимает TestRequest -> возвращает TestResponse.
import logging
from typing import Optional
from api_client import GigaChatAPIClient
from prompt_builder import PromptBuilder
from response_parser import ResponseParser
from schemas import TestRequest, TestResponse

logger = logging.getLogger(__name__)

class TestGenerator:
    """
    Главный класс генератора тестов.
    Координирует работу всех компонентов.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_client = GigaChatAPIClient(api_key)
        self.prompt_builder = PromptBuilder()
        self.response_parser = ResponseParser()
    
    async def generate_test(self, request: TestRequest) -> TestResponse:
        """
        Основной метод: принимает запрос, возвращает сгенерированный тест.
        
        Процесс:
        1. Преобразуем TestRequest в промпт
        2. Отправляем промпт в GigaChat API
        3. Получаем сырой JSON ответ
        4. Парсим ответ
        5. Валидируем через Pydantic
        6. Возвращаем TestResponse
        
        Args:
            request: Запрос на генерацию теста
            
        Returns:
            Сгенерированный тест
        """
        logger.info(f"Начинаю генерацию теста: {request.num_questions} вопросов")
        
        try:
            # 1. Строим промпт из запроса
            prompt = self.prompt_builder.build_test_generation_prompt(request)
            messages = self.prompt_builder.prepare_messages(prompt)
            
            logger.debug(f"Построен промпт длиной {len(prompt)} символов")
            
            # 2. Отправляем запрос в API
            raw_response = await self.api_client.send_request(
                messages=messages,
                max_tokens=4000,  # Для теста из 10 вопросов
                temperature=0.7
            )
            
            logger.debug("Получен сырой ответ от API")
            
            # 3. Извлекаем сгенерированный текст
            content = self.response_parser.extract_content_from_response(raw_response)
            logger.debug(f"Извлечен контент длиной {len(content)} символов")
            
            # 4. Парсим JSON из текста
            parsed_data = self.response_parser.parse_json_response(content)
            logger.debug(f"JSON успешно распарсен, ключи: {list(parsed_data.keys())}")
            
            # 5. Валидируем через Pydantic
            test_response = TestResponse(**parsed_data)
            
            logger.info(f"Тест успешно сгенерирован: тема='{test_response.topic}'")
            return test_response
            
        except Exception as e:
            logger.error(f"Ошибка генерации теста: {str(e)}")
            raise
    
    async def is_available(self) -> bool:
        """Проверяет доступность GigaChat API"""
        return await self.api_client.check_availability()
