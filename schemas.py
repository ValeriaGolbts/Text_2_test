# валидация входа 
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from enum import Enum

class QuestionType(str, Enum):
    """Типы вопросов"""
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"

class Question(BaseModel):
    """Модель одного вопроса"""
    question: str = Field(..., description="Текст вопроса")
    type: QuestionType = Field(..., description="Тип вопроса")
    options: List[str] = Field(default_factory=list, description="Варианты ответов")
    correct_answer: str | List[str] = Field(..., description="Правильный ответ")
    explanation: Optional[str] = Field(None, description="Объяснение ответа")
    difficulty: Literal["easy", "medium", "hard"] = Field("medium", description="Сложность")

class TestRequest(BaseModel):
    """Что принимает генератор (входные данные)"""
    text_material: str = Field(..., description="Предобработанный текст материала")
    num_questions: int = Field(10, ge=1, le=50, description="Количество вопросов")
    difficulty: Literal["easy", "medium", "hard"] = Field("medium", description="Сложность")
    question_types: List[QuestionType] = Field(
        default_factory=lambda: [QuestionType.SINGLE_CHOICE],
        description="Типы вопросов"
    )
    topic: Optional[str] = Field(None, description="Конкретная тема (если нужно)")

class TestResponse(BaseModel):
    """Что возвращает генератор (результат)"""
    questions: List[Question] = Field(..., description="Список вопросов")
    topic: str = Field(..., description="Тема теста")
    total_questions: int = Field(..., description="Общее количество вопросов")
    estimated_time_minutes: int = Field(..., description="Предполагаемое время прохождения")
    
    @validator('total_questions')
    def validate_total_questions(cls, v, values):
        if 'questions' in values and len(values['questions']) != v:
            raise ValueError(
                f"total_questions={v}, но questions содержит {len(values['questions'])} вопросов"
            )
        return v
