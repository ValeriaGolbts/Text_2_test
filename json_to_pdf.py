import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Регистрация шрифта с поддержкой кириллицы (если есть файл шрифта)
try:
    pdfmetrics.registerFont(TTFont('DejaVu', 'DejaVuSans.ttf'))  # скачайте DejaVuSans.ttf или используйте системный
except:
    # fallback — используем стандартный, но кириллица может не отображаться
    pass

def json_to_pdf(json_file_path, output_pdf_path):
    # Загрузка JSON
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Стили
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontName='Helvetica',
        fontSize=18,
        alignment=TA_LEFT,
        spaceAfter=12
    )
    subject_style = ParagraphStyle(
        'SubjectStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        textColor='darkblue',
        spaceAfter=6
    )
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        spaceAfter=6,
        spaceBefore=12
    )
    option_style = ParagraphStyle(
        'OptionStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leftIndent=20,
        spaceAfter=3
    )
    explanation_style = ParagraphStyle(
        'ExplanationStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        textColor='green',
        leftIndent=20,
        spaceAfter=12
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor='gray'
    )

    # Создание PDF
    doc = SimpleDocTemplate(output_pdf_path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []

    # Заголовок
    story.append(Paragraph(data.get('test_title', 'Тест'), title_style))
    story.append(Paragraph(f"Предмет: {data.get('subject', 'Не указан')}", subject_style))
    story.append(Paragraph(f"Сложность: {data.get('difficulty', 'Не указана')}", subject_style))
    story.append(Spacer(1, 0.5*cm))

    # Вопросы
    for q in data.get('questions', []):
        q_text = f"{q.get('id')}. {q.get('question')}"
        story.append(Paragraph(q_text, question_style))
        
        # Варианты ответов
        options = q.get('options', [])
        for idx, opt in enumerate(options, start=1):
            # Помечаем правильный ответ звёздочкой или галочкой (по желанию)
            marker = "✓ " if opt == q.get('correct_answer') else "• "
            story.append(Paragraph(f"{marker}{opt}", option_style))
        
        # Объяснение
        exp = q.get('explanation', '')
        if exp:
            story.append(Paragraph(f"<i>Объяснение:</i> {exp}", explanation_style))
        
        story.append(Spacer(1, 0.3*cm))

    # Метаданные
    story.append(PageBreak())
    story.append(Paragraph("Метаданные обработки", subject_style))
    meta = data.get('pipeline_metadata', {})
    story.append(Paragraph(f"Исходный файл: {meta.get('source_file', '')}", meta_style))
    story.append(Paragraph(f"Время обработки: {meta.get('processed_at', '')}", meta_style))
    stats = meta.get('statistics', {})
    story.append(Paragraph(f"Всего чанков: {stats.get('total_chunks', '')}", meta_style))
    story.append(Paragraph(f"Всего формул: {stats.get('total_formulas', '')}", meta_style))
    story.append(Paragraph(f"Время обработки (сек): {stats.get('processing_time_seconds', '')}", meta_style))

    # Сборка документа
    doc.build(story)
    print(f"PDF сохранён: {output_pdf_path}")

if __name__ == "__main__":
    # Пример использования
    input_json = "test_result_20260424_140612.json"   # укажите ваш JSON-файл
    output_pdf = "finish_test.pdf"
    if os.path.exists(input_json):
        json_to_pdf(input_json, output_pdf)
    else:
        print(f"Файл {input_json} не найден. Укажите правильный путь.")
