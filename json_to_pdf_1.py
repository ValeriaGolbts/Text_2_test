#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image as PILImage

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
# 2. Нормализация LaTeX-выражения
# ----------------------------------------------------------------------
def normalize_latex(latex_expr):
    """
    Нормализует LaTeX-выражение, убирая двойное экранирование.
    """
    latex_expr = latex_expr.replace('\\\\', '\\')
    return latex_expr

# ----------------------------------------------------------------------
# 3. Конвертация LaTeX-формулы в PNG-изображение
# ----------------------------------------------------------------------
def latex_to_image(latex_expr, fontsize=20):
    """
    Преобразует строку с LaTeX в PNG и возвращает путь к файлу.
    """
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name

    latex_expr = normalize_latex(latex_expr)
    
    fig, ax = plt.subplots(figsize=(6, 1.0))
    ax.axis('off')
    
    latex_string = f"${latex_expr}$"
    
    try:
        ax.text(0.0, 0.5, latex_string, 
                ha='left', va='center', 
                fontsize=fontsize,
                transform=ax.transAxes)
    except Exception as e:
        print(f"Ошибка рендеринга формулы '{latex_expr}': {e}")
        ax.text(0.0, 0.5, f"[Formula]", 
                ha='left', va='center', 
                fontsize=10,
                transform=ax.transAxes)
    
    plt.savefig(tmp_path, dpi=200, bbox_inches='tight', 
                pad_inches=0.05, transparent=False,
                facecolor='white', format='png')
    plt.close(fig)

    pil_img = PILImage.open(tmp_path)
    img_width, img_height = pil_img.size
    
    img = Image(tmp_path)
    
    target_height = 1.2 * cm
    aspect_ratio = img_width / img_height if img_height > 0 else 1
    target_width = target_height * aspect_ratio
    
    max_width = 15 * cm
    if target_width > max_width:
        target_width = max_width
        target_height = target_width / aspect_ratio
    
    img.drawHeight = target_height
    img.drawWidth = target_width
    img.hAlign = 'LEFT'
    
    return img, tmp_path

# ----------------------------------------------------------------------
# 4. Разбиение строки на текст и формулы
# ----------------------------------------------------------------------
def split_text_and_formulas(text):
    """
    Разделяет строку на части: текст и LaTeX-выражения (внутри $...$).
    """
    parts = []
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
            latex_expr = normalize_latex(latex_expr)
            parts.append(('latex', latex_expr))
        last_end = end
    
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            parts.append(('text', remaining))
    
    return parts

# ----------------------------------------------------------------------
# 5. Создание одного Paragraph с формулами как <img> тегами
# ----------------------------------------------------------------------
def create_inline_paragraph(content, style):
    """
    Создает один Paragraph, где формулы вставлены как <img> теги.
    Возвращает Paragraph и список временных файлов.
    """
    parts = split_text_and_formulas(content)
    temp_files = []
    paragraph_parts = []
    
    for typ, value in parts:
        if typ == 'text':
            clean_text = ' '.join(value.split())
            if clean_text:
                # Экранируем XML-спецсимволы
                clean_text = clean_text.replace('&', '&amp;')
                clean_text = clean_text.replace('<', '&lt;')
                clean_text = clean_text.replace('>', '&gt;')
                paragraph_parts.append(clean_text)
        else:  # latex
            try:
                img, tmp_path = latex_to_image(value)
                temp_files.append(tmp_path)
                
                # Создаем <img> тег с правильными размерами
                img_tag = f'<img src="{tmp_path}" width="{img.drawWidth}" height="{img.drawHeight}" valign="middle"/>'
                paragraph_parts.append(img_tag)
            except Exception as e:
                print(f"Ошибка при конвертации формулы '{value}': {e}")
                paragraph_parts.append(f"${value}$")
    
    # Собираем все части в одну строку
    full_text = ''.join(paragraph_parts)
    
    # Создаем Paragraph
    para = Paragraph(full_text, style)
    
    return para, temp_files

# ----------------------------------------------------------------------
# 6. Основная функция конвертации
# ----------------------------------------------------------------------
def json_to_pdf_questions_only(json_path, pdf_path):
    print(f"Открытие JSON файла: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    questions = data.get('questions')
    if not questions:
        print("Нет вопросов в JSON.")
        return

    print(f"Найдено вопросов: {len(questions)}")
    
    font_name = register_cyrillic_font()
    print(f"Используемый шрифт: {font_name}")
    
    styles = getSampleStyleSheet()
    
    # Базовый стиль для текста
    text_style = ParagraphStyle(
        'Text', 
        parent=styles['Normal'], 
        fontName=font_name,
        fontSize=12, 
        leading=18,  # Увеличен для формул
        encoding='utf-8'
    )
    
    # Стиль для вопроса
    question_style = ParagraphStyle(
        'Question', 
        parent=text_style, 
        fontSize=12, 
        leading=18,
        spaceAfter=4,
        spaceBefore=4,
        fontName=font_name
    )
    
    # Стиль для вариантов ответов
    option_style = ParagraphStyle(
        'Option', 
        parent=text_style, 
        fontSize=12, 
        leading=18,
        leftIndent=20,
        spaceAfter=2,
        spaceBefore=2,
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

    # Заголовок теста
    test_title = data.get('test_title')
    if test_title:
        title_style = ParagraphStyle(
            'Title', 
            parent=text_style, 
            fontSize=16,
            leading=22,
            spaceAfter=8, 
            fontName=font_name,
            alignment=TA_CENTER
        )
        story.append(Paragraph(test_title, title_style))
        story.append(Spacer(1, 0.3*cm))

    # Обработка вопросов
    for q in questions:
        q_id = q.get('id', '?')
        q_text = q.get('question', '')
        if not q_text:
            continue

        print(f"\nОбработка вопроса {q_id}: {q_text[:60]}...")
        
        # Вопрос
        question_text = f"{q_id}. {q_text}"
        para, temps = create_inline_paragraph(question_text, question_style)
        all_temp_files.extend(temps)
        story.append(para)

        # Варианты ответов
        options = q.get('options', [])
        for idx, opt in enumerate(options):
            if idx < 26:
                letter = chr(65 + idx)
                option_text = f"{letter}) {opt}"
                para, temps = create_inline_paragraph(option_text, option_style)
                all_temp_files.extend(temps)
                story.append(para)

        # Отступ между вопросами
        story.append(Spacer(1, 0.4*cm))

    # Сборка PDF
    print(f"\nСоздание PDF...")
    try:
        doc.build(story)
        print(f"PDF успешно создан: {pdf_path}")
    except Exception as e:
        print(f"Ошибка при создании PDF: {e}")
        import traceback
        traceback.print_exc()

    # Очистка временных файлов
    print(f"Очистка {len(all_temp_files)} временных файлов...")
    for f in all_temp_files:
        try:
            if os.path.exists(f):
                os.unlink(f)
        except:
            pass

if __name__ == "__main__":
    input_json = "res_fin.json"
    output_pdf = "questions_output.pdf"
    
    if os.path.exists(input_json):
        json_to_pdf_questions_only(input_json, output_pdf)
    else:
        print(f"Файл {input_json} не найден.")
