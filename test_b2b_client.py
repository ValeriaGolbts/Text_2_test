# scripts/test_b2b_client.py
import sys
import os
from pathlib import Path
import asyncio

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api_client_b2b import GigaChatB2BClient
from config import config

async def main():
    print(" ТЕСТ ПЕРВЫЙ. ПРОВЕРКА СВЯЗИ")    
    print(f"Конфигурация:")
    print(f"Модель: {config.GIGACHAT_MODEL}")
    print(f"Scope: {getattr(config, 'GIGACHAT_SCOPE', 'не указан')}")
    print(f"Ключ: {config.GIGACHAT_API_KEY[:25]}...")
    
    try:
        # Создаем клиент
        print(f"\n B2B клиент.")
        client = GigaChatB2BClient()
        print(f"Клиент создан")
        print(f"RqUID: {client.get_rquid()}")
        
        # Проверяем доступность
        print(f"\n Проверка доступа API")
        is_available = await client.check_availability()
        
        if is_available:
            print(f"API доступен!")
            
            # Тестовый запрос
            print(f"\n Отправляю тестовый запрос.")
            messages = [
                {"role": "user", "content": "Создай 2 тестовых вопроса по точным наукам"}
            ]
            
            response = await client.send_request(
                messages=messages,
                max_tokens=200,
                temperature=0.7
            )
            
            print(f"Запрос выполнен!")
            print(f"\n Ответ:")
            print(response['choices'][0]['message']['content'])
            
        else:
            print(f"Ошибка.API недоступен.")
            
    except Exception as e:
        print(f"Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
    input("\nНажмите Enter для выхода...")
