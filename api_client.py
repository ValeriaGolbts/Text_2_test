# api_client.py - Обновленная версия с использованием официальной библиотеки gigachat
import logging
from typing import Dict, Any, Optional
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from config import config

logger = logging.getLogger(__name__)

class GigaChatAPIClient:
    """Клиент для GigaChat API на основе официальной библиотеки"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GIGACHAT_API_KEY
        
        # Инициализируем клиент GigaChat
        self.client = GigaChat(
            credentials=self.api_key,
            model=config.GIGACHAT_MODEL,
            timeout=config.GIGACHAT_TIMEOUT,
            verify_ssl_certs=False  # Отключаем проверку SSL для тестирования
        )
        
        logger.debug(f"Инициализирован клиент GigaChat для модели: {config.GIGACHAT_MODEL}")
    
    async def send_request(self, messages: list, **kwargs) -> Dict[str, Any]:
        """
        Отправляет запрос в GigaChat API.
        
        Args:
            messages: Список сообщений в формате [{"role": "user", "content": "текст"}]
            **kwargs: Дополнительные параметры (max_tokens, temperature, etc.)
            
        Returns:
            Ответ от API в формате словаря
        """
        try:
            # Преобразуем сообщения в формат GigaChat
            giga_messages = []
            for msg in messages:
                giga_messages.append(
                    Messages(
                        role=MessagesRole(msg["role"]),
                        content=msg["content"]
                    )
                )
            
            # Создаем чат
            chat = Chat(
                messages=giga_messages,
                model=kwargs.get("model", config.GIGACHAT_MODEL),
                max_tokens=kwargs.get("max_tokens", config.GIGACHAT_MAX_TOKENS),
                temperature=kwargs.get("temperature", config.GIGACHAT_TEMPERATURE),
            )
            
            logger.debug(f"Отправка запроса к GigaChat API")
            logger.debug(f"Параметры: model={chat.model}, tokens={chat.max_tokens}")
            
            # Отправляем запрос
            response = await self.client.achat(chat)
            
            # Преобразуем ответ в словарь
            result = {
                "choices": [
                    {
                        "message": {
                            "role": response.choices[0].message.role.value,
                            "content": response.choices[0].message.content
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                } if response.usage else None
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса: {str(e)}")
            raise
    
    async def check_availability(self) -> bool:
        """Проверяет доступность API и валидность ключа"""
        try:
            # Простой тестовый запрос
            test_messages = [{"role": "user", "content": "Привет"}]
            response = await self.send_request(
                messages=test_messages,
                max_tokens=5
            )
            
            # Проверяем, что есть ответ
            if response and "choices" in response and len(response["choices"]) > 0:
                logger.info("✅ GigaChat API доступен")
                return True
            return False
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Ошибка проверки API: {error_msg}")
            
            # Анализируем ошибку
            if "401" in error_msg or "Unauthorized" in error_msg:
                logger.error("🔑 ОШИБКА: Неверный API ключ")
                logger.error(f"   • Ключ (первые 20 символов): {self.api_key[:20]}...")
                logger.error("   • Проверьте ключ на https://developers.sber.ru")
            elif "404" in error_msg:
                logger.error("🔍 ОШИБКА: Модель не найдена")
                logger.error(f"   • Модель: {config.GIGACHAT_MODEL}")
                logger.error("   • Попробуйте изменить модель в .env")
            
            return False
