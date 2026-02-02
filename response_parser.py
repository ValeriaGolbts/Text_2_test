# Парсинг сырого JSON ответа от GigaChat.
import json
import logging
from typing import Dict, Any
from schemas import TestResponse, Question

logger = logging.getLogger(__name__)

class ResponseParser:
    """Парсит ответы от GigaChat API"""
    
    @staticmethod
    def extract_content_from_response(api_response: Dict[str, Any]) -> str:
        """
        Извлекает сгенерированный текст из сырого JSON ответа API.
        
        Args:
            api_response: Сырой JSON ответ от GigaChat API
            
        Returns:
            Текст, сгенерированный моделью
        """
        try:
            # Стандартная структура ответа GigaChat
            if "choices" in api_response and len(api_response["choices"]) > 0:
                choice = api_response["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    content = choice["message"]["content"]
                    
                    # Логируем использование токенов
                    if "usage" in api_response:
                        usage = api_response["usage"]
                        logger.info(
                            f"Использовано токенов: "
                            f"prompt={usage.get('prompt_tokens', 0)}, "
                            f"completion={usage.get('completion_tokens', 0)}, "
                            f"total={usage.get('total_tokens', 0)}"
                        )
                    
                    return content
            
            logger.error(f"Неожиданная структура ответа: {api_response}")
            raise ValueError("Неожиданная структура ответа от GigaChat API")
            
        except (KeyError, IndexError) as e:
            logger.error(f"Ошибка извлечения контента: {e}, response: {api_response}")
            raise ValueError(f"Ошибка парсинга ответа: {str(e)}")
    
    @staticmethod
    def parse_json_response(content: str) -> Dict[str, Any]:
        """
        Парсит JSON из сгенерированного текста.
        Очищает от возможных markdown оберток.
        
        Args:
            content: Текст ответа от GigaChat
            
        Returns:
            Распарсенный JSON как словарь
        """
        # Очищаем от markdown оберток (```json ... ```)
        cleaned_content = content.strip()
        
        if "```json" in cleaned_content:
            cleaned_content = cleaned_content.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_content:
            cleaned_content = cleaned_content.split("```")[1].strip()
        
        try:
            return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.error(f"Содержимое: {cleaned_content[:500]}...")
            raise ValueError(f"Неверный JSON формат: {str(e)}")
