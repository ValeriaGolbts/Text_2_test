# Модуль для генерации тестов с использованием GigaChat API.
from test_generator import TestGenerator
from schemas import TestRequest, TestResponse, Question, QuestionType

__all__ = [
    'TestGenerator',      # Главный класс
    'TestRequest',        # Модель запроса (что принимаем)
    'TestResponse',       # Модель ответа (что возвращаем)
    'Question',           # Модель вопроса
    'QuestionType',       # Типы вопросов
]
