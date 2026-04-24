#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def find_cyrillic_font():
    """Возвращает путь к системному шрифту с кириллицей или None."""
    possible_paths = [
        "DejaVuSans.ttf",                        # если файл лежит рядом
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def register_cyrillic_font():
    """Регистрирует шрифт с поддержкой кириллицы. Возвращает имя шрифта."""
    font_path = find_cyrillic_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont('CyrFont', font_path))
            return 'CyrFont'
        except:
            pass
    # Если шрифт не найден — используем Helvetica, но кириллица будет кракозябрами
    print("Предупреждение: не найден шрифт с кириллицей. Русский текст может отображаться некорректно.")
    return 'Helvetica'

def json_to_pdf_questions_only(json_path, pdf_path):
    """Конвертирует JSON-тест в PDF, содержащий только вопросы и варианты ответов."""
    # Загрузка JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Ошибка чтения JSON: {e}")
        return

    questions = data.get('questions')
    if not questions:
        print("В JSON нет ключа 'questions' или он пуст.")
        return

    # Регистрируем шрифт
    font_name = register_cyrillic_font()

    # Стили
    styles = getSampleStyleSheet()
    base_style = ParagraphStyle(
        'Base',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=11,
        leading=14,
    )
    question_style = ParagraphStyle(
        'Question',
        parent=base_style,
        fontName=font_name,
        fontSize=12,
        leading=16,
        spaceAfter=6,
        spaceBefore=12,
        fontWeight='bold',
    )
    option_style = ParagraphStyle(
        'Option',
        parent=base_style,
        fontSize=11,
        leading=14,
        leftIndent=20,
        spaceAfter=3,
    )

    # Создание документа
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    story = []

    # Необязательный заголовок (можно убрать, если нужно только вопросы)
    test_title = data.get('test_title')
    if test_title:
        title_style = ParagraphStyle('Title', parent=base_style, fontSize=16, spaceAfter=12, fontWeight='bold')
        story.append(Paragraph(test_title, title_style))
        story.append(Spacer(1, 0.5*cm))

    # Вопросы и варианты ответов
    for q in questions:
        q_id = q.get('id', '?')
        q_text = q.get('question', '')
        if not q_text:
            continue

        # Сам вопрос
        story.append(Paragraph(f"{q_id}. {q_text}", question_style))

        # Варианты ответов (A, B, C, ...)
        options = q.get('options', [])
        for idx, opt in enumerate(options):
            letter = chr(65 + idx)  # A, B, C, ...
            story.append(Paragraph(f"{letter}. {opt}", option_style))

        # Отступ после вопроса
        story.append(Spacer(1, 0.3*cm))

    # Сборка PDF
    doc.build(story)
    print(f"PDF с вопросами сохранён: {pdf_path}")

if __name__ == "__main__":
    # Пример использования
    input_json = "test_result_20260424_140612.json"   # ваш файл
    output_pdf = "questions_only.pdf"
    if os.path.exists(input_json):
        json_to_pdf_questions_only(input_json, output_pdf)
    else:
        print(f"Файл {input_json} не найден. Укажите правильный путь в коде или передайте аргументы.")
        if len(sys.argv) == 3:
            json_to_pdf_questions_only(sys.argv[1], sys.argv[2])
