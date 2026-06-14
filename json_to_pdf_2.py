# ----------------------------------------------------------------------
# 5. Создание параграфа с формулами
# ----------------------------------------------------------------------
def create_inline_paragraph(content, style, base_font_size=15):  # Увеличено с 12 до 15
    """
    Создает Paragraph с формулами как <img> тегами.
    Исправленная версия с правильными размерами изображений.
    """
    parts = split_text_and_formulas(content)
    temp_files = []
    paragraph_parts = []
    
    for typ, value in parts:
        if typ == 'text':
            # Нормализуем пробелы в тексте
            clean_text = ' '.join(value.split())
            if clean_text:
                # Экранируем XML-спецсимволы
                clean_text = (clean_text
                    .replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                    .replace('"', '&quot;'))
                paragraph_parts.append(clean_text)
        else:  # latex
            try:
                # Создаем изображение формулы с увеличенным размером
                img, tmp_path = latex_to_image(value, fontsize=base_font_size + 5)  # Увеличено на 5
                temp_files.append(tmp_path)
                
                # Создаем <img> тег с правильными размерами
                img_tag = f'<img src="{tmp_path}" width="{img.drawWidth}" height="{img.drawHeight}" valign="middle"/>'
                paragraph_parts.append(img_tag)
            except Exception as e:
                print(f"Ошибка при конвертации формулы '{value}': {e}")
                # В случае ошибки показываем формулу как текст
                paragraph_parts.append(f"${value}$")
    
    # Собираем все части
    full_text = ''.join(paragraph_parts)
    
    # Добавляем небольшой отступ для формул
    if full_text:
        para = Paragraph(full_text, style)
        return para, temp_files
    else:
        return Paragraph(' ', style), temp_files
