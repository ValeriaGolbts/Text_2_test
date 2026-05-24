#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import Flowable
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
# 2. Конвертация LaTeX-формулы в PNG-изображение (УВЕЛИЧЕННЫЙ РАЗМЕР)
# ----------------------------------------------------------------------
def latex_to_image(latex_expr, fontsize=20):
    """
    Преобразует строку с LaTeX в PNG и возвращает объект ReportLab Image.
    """
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name

    # Создаем фигуру
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
                pad_inches=0.1, transparent=False,
                facecolor='white', format='png')
    plt.close(fig)

    # Получаем реальные размеры изображения
    pil_img = PILImage.open(tmp_path)
    img_width, img_height = pil_img.size
    
    # Создаём объект Image reportlab
    img = Image(tmp_path)
    
    # Устанавливаем размер формулы в 3 раза больше текста (текст ~4мм, формула ~12мм)
    target_height = 1.2 * cm  # Высота формулы в 3 раза больше текста
    aspect_ratio = img_width / img_height if img_height > 0 else 1
    target_width = target_height * aspect_ratio
    
    # Ограничиваем максимальную ширину
    max_width = 15 * cm
    if target_width > max_width:
        target_width = max_width
        target_height = target_width / aspect_ratio
    
    img.drawHeight = target_height
    img.drawWidth = target_width
    
    return img, tmp_path

# ----------------------------------------------------------------------
# 3. Разбиение строки на текст и формулы
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
            parts.append(('latex', latex_expr))
        last_end = end
    
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            parts.append(('text', remaining))
    
    return parts

# ----------------------------------------------------------------------
# 4. Создание смешанного параграфа (текст + формулы в одной строке)
# ----------------------------------------------------------------------
class InlineFormulaParagraph(Flowable):
    """Flowable, который объединяет текст и формулы в одной строке."""
    
    def __init__(self, content, style, font_name='CyrFont'):
        Flowable.__init__(self)
        self.content = content
        self.style = style
        self.font_name = font_name
        self.temp_files = []
        self._setup()
    
    def _setup(self):
        """Подготавливает элементы для отображения."""
        self.elements = []
        parts = split_text_and_formulas(self.content)
        
        for typ, value in parts:
            if typ == 'text':
                clean_text = ' '.join(value.split())
                if clean_text:
                    clean_text = clean_text.replace('&', '&amp;')
                    clean_text = clean_text.replace('<', '&lt;')
                    clean_text = clean_text.replace('>', '&gt;')
                    self.elements.append(('text', clean_text))
            else:  # latex
                try:
                    img, tmp_path = latex_to_image(value)
                    self.temp_files.append(tmp_path)
                    self.elements.append(('image', img))
                except Exception as e:
                    print(f"Ошибка при конвертации формулы '{value}': {e}")
                    self.elements.append(('text', f"${value}$"))
    
    def wrap(self, availWidth, availHeight):
        """Определяет размеры Flowable."""
        self.availWidth = availWidth
        # Рассчитываем общую высоту и ширину
        max_height = 0
        total_width = 0
        
        for elem_type, elem in self.elements:
            if elem_type == 'text':
                # Создаем временный параграф для измерения
                p = Paragraph(elem, self.style)
                w, h = p.wrap(availWidth, availHeight)
                max_height = max(max_height, h)
                total_width += w
            else:  # image
                max_height = max(max_height, elem.drawHeight)
                total_width += elem.drawWidth
        
        self.height = max_height
        self.width = min(total_width, availWidth)
        return (self.width, self.height)
    
    def draw(self):
        """Отрисовывает элементы в одной строке."""
        canvas = self.canv
        x = 0
        y = 0
        
        for elem_type, elem in self.elements:
            if elem_type == 'text':
                p = Paragraph(elem, self.style)
                w, h = p.wrap(self.availWidth - x, self.height)
                p.drawOn(canvas, x, y + (self.height - h) / 2)
                x += w
            else:  # image
                elem.drawOn(canvas, x, y + (self.height - elem.drawHeight) / 2)
                x += elem.drawWidth

# ----------------------------------------------------------------------
# 5. Основная функция конвертации
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
        leading=14,
        encoding='utf-8'
    )
    
    # Стиль для вопроса
    question_style = ParagraphStyle(
        'Question', 
        parent=text_style, 
        fontSize=12, 
        leading=14,
        spaceAfter=6, 
        spaceBefore=8,
        fontName=font_name
    )
    
    # Стиль для вариантов ответов
    option_style = ParagraphStyle(
        'Option', 
        parent=text_style, 
        fontSize=12, 
        leading=14,
        leftIndent=20,
        spaceAfter=3,
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
            leading=18,
            spaceAfter=12, 
            fontName=font_name,
            alignment=TA_CENTER
        )
        story.append(Paragraph(test_title, title_style))
        story.append(Spacer(1, 0.5*cm))

    # Обработка вопросов
    for q in questions:
        q_id = q.get('id', '?')
        q_text = q.get('question', '')
        if not q_text:
            continue

        print(f"\nОбработка вопроса {q_id}")
        
        # Вопрос с формулами в одной строке
        question_text = f"{q_id}. {q_text}"
        inline_q = InlineFormulaParagraph(question_text, question_style, font_name)
        all_temp_files.extend(inline_q.temp_files)
        story.append(inline_q)
        story.append(Spacer(1, 0.2*cm))

        # Варианты ответов
        options = q.get('options', [])
        for idx, opt in enumerate(options):
            if idx < 26:
                letter = chr(65 + idx)
                option_text = f"{letter}) {opt}"
                inline_opt = InlineFormulaParagraph(option_text, option_style, font_name)
                all_temp_files.extend(inline_opt.temp_files)
                story.append(inline_opt)
                story.append(Spacer(1, 0.1*cm))

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
    input_json = "test_result_S1_random_lecture_20260519_191606.json"
    output_pdf = "questions_output.pdf"
    
    if os.path.exists(input_json):
        json_to_pdf_questions_only(input_json, output_pdf)
    else:
        print(f"Файл {input_json} не найден.")
