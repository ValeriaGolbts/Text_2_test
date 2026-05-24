#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# 1. Настройка шрифта для кириллицы
# ----------------------------------------------------------------------
def find_cyrillic_font():
    possible_paths = [
        "DejaVuSans.ttf",
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
    font_path = find_cyrillic_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont('CyrFont', font_path))
            return 'CyrFont'
        except:
            pass
    print("Предупреждение: не найден шрифт с кириллицей.")
    return 'Helvetica'

# ----------------------------------------------------------------------
# 2. Конвертация LaTeX-формулы в PNG-изображение (УВЕЛИЧЕННЫЙ РАЗМЕР)
# ----------------------------------------------------------------------
def latex_to_image(latex_expr, dpi=200, fontsize=16):
    """
    Преобразует строку с LaTeX (без ограничителей $) в PNG и возвращает
    объект ReportLab Image с увеличенным размером.
    """
    # Временный файл для изображения
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name

    # Создаем фигуру большего размера
    fig, ax = plt.subplots(figsize=(8, 1.2))  # Увеличиваем размер фигуры
    ax.axis('off')
    
    # Формируем полную LaTeX-строку
    latex_string = f"${latex_expr}$"
    
    try:
        # Отображаем формулу с увеличенным шрифтом
        ax.text(0.5, 0.5, latex_string, 
                ha='center', va='center', 
                fontsize=fontsize,  # Увеличенный шрифт
                transform=ax.transAxes)
    except Exception as e:
        print(f"Ошибка рендеринга формулы: {e}")
        # Пробуем упрощенный вариант без формул
        simple_text = re.sub(r'\$[^$]*\$', '[формула]', latex_expr)
        ax.text(0.5, 0.5, simple_text, 
                ha='center', va='center', 
                fontsize=fontsize,
                transform=ax.transAxes)
    
    # Сохраняем с высоким разрешением
    plt.savefig(tmp_path, dpi=dpi, bbox_inches='tight', 
                pad_inches=0.15, transparent=True,
                format='png')
    plt.close(fig)

    # Создаём объект Image reportlab с увеличенными размерами
    img = Image(tmp_path)
    
    # Увеличиваем размер изображения в PDF
    img.drawHeight = 0.8 * cm  # Было 0.5, стало 0.8
    img.drawWidth = img.drawWidth * (0.8 / 0.5) if img.drawHeight > 0 else 3 * cm  # Пропорционально увеличиваем ширину
    img.hAlign = 'LEFT'
    
    return img, tmp_path

# ----------------------------------------------------------------------
# 3. Разбиение строки на текст и формулы
# ----------------------------------------------------------------------
def split_text_and_formulas(text):
    """
    Разделяет строку на части: текст и LaTeX-выражения (внутри $...$).
    Возвращает список кортежей ('text', строка) или ('latex', выражение).
    """
    parts = []
    # Ищем все вхождения $...$
    pattern = r'\$([^$]+?)\$'
    matches = re.finditer(pattern, text)
    last_end = 0
    
    for m in matches:
        start, end = m.span()
        if start > last_end:
            plain_text = text[last_end:start]
            if plain_text.strip():
                parts.append(('text', plain_text))
        latex_expr = m.group(1).strip()
        if latex_expr:
            parts.append(('latex', latex_expr))
        last_end = end
    
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            parts.append(('text', remaining))
    
    return parts

# ----------------------------------------------------------------------
# 4. Создание списка элементов для PDF из разбитой строки
# ----------------------------------------------------------------------
def parse_content_to_flowables(content, base_style, is_inline=False):
    """
    Принимает строку с возможными формулами $...$.
    Возвращает список flowable элементов (Paragraph для текста, Image для формул).
    is_inline - если True, формулы будут меньшего размера для встраивания в текст
    """
    elements = []
    parts = split_text_and_formulas(content)
    temp_files = []
    
    for typ, value in parts:
        if typ == 'text':
            # Очищаем текст от лишних пробелов
            clean_text = ' '.join(value.split())
            if clean_text:
                # Заменяем специальные HTML-символы если есть
                clean_text = clean_text.replace('&', '&amp;')
                clean_text = clean_text.replace('<', '&lt;')
                clean_text = clean_text.replace('>', '&gt;')
                elements.append(Paragraph(clean_text, base_style))
        else:  # latex
            try:
                # Для инлайн формул используем меньший размер
                if is_inline:
                    img, tmp_path = latex_to_image(value, dpi=150, fontsize=12)
                    img.drawHeight = 0.6 * cm
                else:
                    img, tmp_path = latex_to_image(value)
                
                temp_files.append(tmp_path)
                elements.append(img)
                elements.append(Spacer(1, 0.15*cm))  # Немного увеличенный отступ
            except Exception as e:
                print(f"Ошибка при конвертации формулы '{value}': {e}")
                # В случае ошибки показываем формулу как текст
                elements.append(Paragraph(f"${value}$", base_style))
    
    return elements, temp_files

# ----------------------------------------------------------------------
# 5. Основная функция конвертации (только вопросы и варианты ответов)
# ----------------------------------------------------------------------
def json_to_pdf_questions_only(json_path, pdf_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    questions = data.get('questions')
    if not questions:
        print("Нет вопросов в JSON.")
        return

    font_name = register_cyrillic_font()
    styles = getSampleStyleSheet()
    
    # Создаем стили
    base_style = ParagraphStyle(
        'Base', 
        parent=styles['Normal'], 
        fontName=font_name,
        fontSize=12,  # Увеличиваем базовый шрифт
        leading=16,   # Увеличиваем межстрочный интервал
        encoding='utf-8'
    )
    
    question_style = ParagraphStyle(
        'Question', 
        parent=base_style, 
        fontSize=14,  # Увеличиваем шрифт вопросов
        leading=18,
        spaceAfter=10, 
        spaceBefore=14,
        fontName=font_name
    )
    
    option_style = ParagraphStyle(
        'Option', 
        parent=base_style, 
        fontSize=12,  # Увеличиваем шрифт вариантов
        leading=16,
        leftIndent=25,  # Увеличиваем отступ
        spaceAfter=6,
        fontName=font_name
    )

    doc = SimpleDocTemplate(
        pdf_path, 
        pagesize=A4,
        rightMargin=2*cm, 
        leftMargin=2*cm,
        topMargin=2*cm, 
        bottomMargin=2*cm
    )
    
    story = []
    all_temp_files = []

    # Заголовок теста (если есть)
    test_title = data.get('test_title')
    if test_title:
        title_style = ParagraphStyle(
            'Title', 
            parent=base_style, 
            fontSize=18,  # Увеличиваем шрифт заголовка
            leading=22,
            spaceAfter=16, 
            fontName=font_name,
            alignment=1  # Центрирование
        )
        story.append(Paragraph(test_title, title_style))
        story.append(Spacer(1, 0.8*cm))  # Увеличиваем отступ

    # Обработка вопросов
    for q in questions:
        q_id = q.get('id', '?')
        q_text = q.get('question', '')
        if not q_text:
            continue

        # Вопрос
        full_question = f"{q_id}. {q_text}"
        print(f"Обработка вопроса {q_id}...")
        q_elements, temps = parse_content_to_flowables(full_question, question_style)
        all_temp_files.extend(temps)
        story.extend(q_elements)

        # Варианты ответов
        options = q.get('options', [])
        for idx, opt in enumerate(options):
            if idx < 26:  # Только буквы A-Z
                letter = chr(65 + idx)
                opt_text = f"{letter}) {opt}"
                # Для вариантов ответов используем инлайн режим
                opt_elements, temps = parse_content_to_flowables(opt_text, option_style, is_inline=True)
                all_temp_files.extend(temps)
                story.extend(opt_elements)

        # Отступ между вопросами
        story.append(Spacer(1, 0.8*cm))  # Увеличиваем отступ

    # Сборка PDF
    try:
        doc.build(story)
        print(f"PDF успешно создан: {pdf_path}")
    except Exception as e:
        print(f"Ошибка при создании PDF: {e}")

    # Очистка временных файлов
    for f in all_temp_files:
        try:
            if os.path.exists(f):
                os.unlink(f)
        except:
            pass

if __name__ == "__main__":
    input_json = "test_result_S1_random_lecture_20260519_191606.json"
    output_pdf = "questions_output.pdf"
    
    if os.path.exists(input_json):
        json_to_pdf_questions_only(input_json, output_pdf)
    else:
        print(f"Файл {input_json} не найден.")
