import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from numbers_desc import (
    action_number_meanings,
    character_number_meanings,
    character_numbers,
    consciousness_number_meanings,
    destiny_number_meanings,
    energy_number_meanings,
    energy_numbers,
    matrix_energies,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

BACKGROUND_COLOR = (0.18, 0.10, 0.32)
PANEL_COLOR = (0.28, 0.19, 0.45)
CONTENT_COLOR = (0.38, 0.27, 0.55)
HEADER_BG = (0.32, 0.22, 0.48)
YELLOW = (0.98, 0.89, 0.26)
TEXT_MAIN = (0.96, 0.95, 0.99)


def _pick_font() -> tuple[str, str]:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        BASE_DIR / "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                pdfmetrics.registerFont(TTFont("ReportFont", str(candidate)))
                return "ReportFont", "ReportFont"
            except Exception as exc:
                logger.warning("Не удалось зарегистрировать шрифт %s: %s", candidate, exc)
    return "Helvetica", "Helvetica"


def _prepare_page_frame(c: canvas.Canvas, margin: float, padding: float) -> tuple[float, float, float, float]:
    page_width, page_height = A4
    content_width = page_width - (margin * 2)
    content_height = page_height - (margin * 2)
    content_x = margin + padding
    content_y = page_height - margin - padding
    c.setFillColorRGB(*BACKGROUND_COLOR)
    c.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    c.setFillColorRGB(*CONTENT_COLOR)
    c.roundRect(margin, margin, content_width, content_height, 10, fill=1, stroke=0)
    return page_width, page_height, content_x, content_y


def _draw_page_title(c: canvas.Canvas, text: str, font_name: str, size: int, margin: float) -> None:
    page_width, page_height = A4
    c.setFillColorRGB(*TEXT_MAIN)
    c.setFont(font_name, size)
    text_width = c.stringWidth(text, font_name, size)
    x = (page_width - text_width) / 2
    c.drawString(x, page_height - margin, text)
    c.setFillColorRGB(*TEXT_MAIN)


def _draw_centered_title(c: canvas.Canvas, text: str, x: float, y: float, width: float, font_name: str, size: int) -> float:
    c.setFillColorRGB(*YELLOW)
    c.setFont(font_name, size)
    text_width = c.stringWidth(text, font_name, size)
    center_x = x + (width - text_width) / 2
    c.drawString(center_x, y, text)
    c.setFillColorRGB(*TEXT_MAIN)
    return y - size - 6


def _draw_title_bar(c: canvas.Canvas, text: str, x: float, y: float, width: float, font_name: str, size: int) -> float:
    # Поднимаем прямоугольник и центрируем текст внутри него
    bar_height = size + 10
    rect_y = y - bar_height + 6  # подняли выше
    c.setFillColorRGB(*HEADER_BG)
    c.roundRect(x, rect_y, width, bar_height, 5, fill=1, stroke=0)

    text_y = rect_y + (bar_height - size) / 2 + 3
    c.setFillColorRGB(*YELLOW)
    c.setFont(font_name, size)
    c.drawString(x + 10, text_y, text)
    c.setFillColorRGB(*TEXT_MAIN)
    return rect_y - 6


def _draw_paragraph(c: canvas.Canvas, text: str, x: float, y: float, width: float, font_name: str, font_size: int, leading: float, page_height: float, margin: float) -> float:
    if not text:
        return y
    lines = simpleSplit(text, font_name, font_size, width)
    y -= 10
    for line in lines:
        if y - leading < margin:
            c.showPage()
            c.setFont(font_name, font_size)
            y = page_height - margin
        c.drawString(x, y, line)
        y -= leading
    return y


def _draw_footer_links(c: canvas.Canvas, page_width: float, margin: float, font_regular: str) -> None:
    left_text = "Сюцай"
    right_text = "@kodsudbblybot"
    link = "https://t.me/kodsudbblybot"
    y = margin * 0.6
    c.setFont(font_regular, 12)
    c.setFillColorRGB(*YELLOW)

    c.drawString(margin, y, left_text)
    left_w = c.stringWidth(left_text, font_regular, 12)
    c.linkURL(link, (margin, y - 2, margin + left_w, y + 10), relative=0)
    c.setLineWidth(0.7)
    c.line(margin, y - 1, margin + left_w, y - 1)

    right_w = c.stringWidth(right_text, font_regular, 12)
    right_x = page_width - margin - right_w
    c.drawString(right_x, y, right_text)
    c.linkURL(link, (right_x, y - 2, right_x + right_w, y + 10), relative=0)
    c.line(right_x, y - 1, right_x + right_w, y - 1)


def _draw_stat_box(c: canvas.Canvas, x: float, y: float, width: float, height: float, title: str, value: str, font_regular: str, font_bold: str) -> None:
    c.setFillColorRGB(*HEADER_BG)
    c.roundRect(x, y, width, height, 10, fill=1, stroke=0)
    c.setFillColorRGB(*YELLOW)
    c.setFont(font_bold, 16)
    c.drawString(x + 10, y + height - 20, title)
    c.setFillColorRGB(*TEXT_MAIN)
    c.setFont(font_bold, 22)
    c.drawString(x + 10, y + height - 50, value)


def _write_section(c: canvas.Canvas, title: str, number: Optional[int], meaning: Optional[dict], y: float, x: float, width: float, font_regular: str, header_font: str, font_bold: str) -> float:
    if number is None or meaning is None:
        return y

    for label_key, text_key in [("Плюс", "plus"), ("Минус", "minus"), ("Комментарий", "comment")]:
        text_value = meaning.get(text_key)
        if not text_value:
            continue
        y = _draw_title_bar(c, label_key, x, y, width, header_font, 14)
        c.setFont(font_regular, 12)
        y = _draw_paragraph(c, text_value, x + 10, y, width - 20, font_regular, 12, 17, 0, 0)
        y -= 12
    y -= 20
    return y


def _write_action_section(c: canvas.Canvas, number: Optional[int], meaning: Optional[dict], y: float, x: float, width: float, font_regular: str, header_font: str, font_bold: str) -> float:
    if number is None or meaning is None:
        return y

    blocks = [
        ("Смысл действия", meaning.get("действие")),
        ("Комментарий", meaning.get("коммент")),
        ("Наставление", meaning.get("наставление")),
        ("Поступки в плюсе", meaning.get("поступки_плюс")),
        ("Поступки в минусе", meaning.get("поступки_минус")),
    ]

    for label, text in blocks:
        if not text:
            continue
        y = _draw_title_bar(c, label, x, y, width, header_font, 14)
        c.setFont(font_regular, 12)
        y = _draw_paragraph(c, text, x + 10, y, width - 20, font_regular, 12, 17, 0, 0)
        y -= 12
    y -= 20
    return y




def _draw_cover_page(c: canvas.Canvas, full_name: str, birth_date: date, consciousness: int, action: Optional[int], destiny: int, character: int, energy: int, font_regular: str, font_bold: str, header_font: str) -> None:
    content_margin = 14 * mm
    content_padding = 8 * mm
    page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)

    y = top_y - 30
    y = _draw_centered_title(c, "Нумерологический отчет", content_x + 10, y, page_width - (content_x + 10) * 2, header_font, 28)

    c.setFont(header_font, 22)
    c.setFillColorRGB(*TEXT_MAIN)
    c.drawString(content_x + 20, y - 8, f"Имя: {full_name}")
    c.drawString(content_x + 20, y - 32, f"Дата рождения: {birth_date.strftime('%d.%m.%Y')}")
    y -= 70

    box_width = page_width - (content_x + 6) * 2
    box_height = 58
    gap = 12
    start_x = content_x + 6
    start_y = y - box_height

    _draw_stat_box(c, start_x, start_y, box_width, box_height, "Число Сознания", str(consciousness), font_regular, font_bold)
    start_y -= box_height + gap
    _draw_stat_box(c, start_x, start_y, box_width, box_height, "Число Судьбы", str(destiny), font_regular, font_bold)
    start_y -= box_height + gap
    _draw_stat_box(c, start_x, start_y, box_width, box_height, "Число Действия", str(action) if action is not None else "—", font_regular, font_bold)
    start_y -= box_height + gap
    _draw_stat_box(c, start_x, start_y, box_width, box_height, "Число Характера", str(character), font_regular, font_bold)
    start_y -= box_height + gap
    _draw_stat_box(c, start_x, start_y, box_width, box_height, "Число Энергии", str(energy), font_regular, font_bold)


def _draw_number_page(c: canvas.Canvas, title: str, number: int, meaning: Optional[dict], font_regular: str, font_bold: str, header_font: str) -> None:
    c.showPage()
    content_margin = 14 * mm
    content_padding = 8 * mm
    page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)
    y = top_y - 30

    y = _draw_centered_title(
        c,
        f"{title}: {number}",
        content_x + 10,
        y,
        page_width - (content_x + 10) * 2,
        header_font,
        24,
    )

    if meaning:
        if title == "Число Характера" and number is not None:
            text = character_numbers.get(number, "")
            if text:
                c.setFont(font_regular, 12)
                y = _draw_paragraph(c, text, content_x + 10, y, page_width - (content_x + 10) * 2, font_regular, 12, 17, 0, 0)
        elif title == "Число Энергии" and number is not None:
            text = energy_numbers.get(number, "")
            if text:
                c.setFont(font_regular, 12)
                y = _draw_paragraph(c, text, content_x + 10, y, page_width - (content_x + 10) * 2, font_regular, 12, 17, 0, 0)
        else:
            y = _write_section(c, title, number, meaning, y, content_x + 10, page_width - (content_x + 10) * 2, font_regular, header_font, font_bold)
    _draw_footer_links(c, page_width, content_margin, font_regular)


def _draw_action_page(c: canvas.Canvas, number: Optional[int], meaning: Optional[dict], font_regular: str, font_bold: str, header_font: str) -> None:
    c.showPage()
    content_margin = 14 * mm
    content_padding = 8 * mm
    page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)
    y = top_y - 30

    y = _draw_centered_title(
        c,
        f"Число Действия: {number if number is not None else '—'}",
        content_x + 10,
        y,
        page_width - (content_x + 10) * 2,
        header_font,
        24,
    )

    if meaning:
        y = _write_action_section(c, number, meaning, y, content_x + 10, page_width - (content_x + 10) * 2, font_regular, header_font, font_bold)
    _draw_footer_links(c, page_width, content_margin, font_regular)




def generate_numerology_report_pdf(user_id: int, full_name: str, birth_date: date) -> Path:
    font_regular, font_bold = _pick_font()
    unique_name = f"razbor.pdf"
    pdf_path = REPORTS_DIR / unique_name

    consciousness = calculate_consciousness_number(birth_date)
    destiny = calculate_destiny_number(birth_date)
    action = calculate_action_number(full_name)
    character = calculate_character_number(birth_date)
    energy = calculate_energy_number(birth_date)

    cons_meaning = consciousness_number_meanings.get(consciousness)
    destiny_meaning = destiny_number_meanings.get(destiny)
    action_meaning = action_number_meanings.get(action)
    character_meaning = character_number_meanings.get(character)
    energy_meaning = energy_number_meanings.get(energy)

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _draw_cover_page(c, full_name, birth_date, consciousness, action, destiny, character, energy, font_regular, font_bold, font_regular)
    _draw_number_page(c, "Число Сознания", consciousness, cons_meaning, font_regular, font_bold, font_regular)
    _draw_number_page(c, "Число Судьбы", destiny, destiny_meaning, font_regular, font_bold, font_regular)
    _draw_action_page(c, action, action_meaning, font_regular, font_bold, font_regular)
    _draw_number_page(c, "Число Характера", character, character_meaning, font_regular, font_bold, font_regular)
    _draw_number_page(c, "Число Энергии", energy, energy_meaning, font_regular, font_bold, font_regular)
    _draw_psychomatrix_page(c, birth_date, font_regular, font_bold, font_regular)
    _draw_innate_energies_page(c, birth_date, font_regular, font_bold, font_regular)
    _draw_missing_energies_page(c, birth_date, font_regular, font_bold, font_regular)
    _draw_missing_energy_details_pages(c, birth_date, font_regular, font_bold, font_regular)
    c.save()
    return pdf_path


def _draw_psychomatrix_page(c: canvas.Canvas, birth_date: date, font_regular: str, font_bold: str, header_font: str) -> None:
    c.showPage()
    content_margin = 14 * mm
    content_padding = 8 * mm
    page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)
    y = top_y - 30

    y = _draw_centered_title(
        c,
        "Матрица врожденных энергий",
        content_x + 10,
        y,
        page_width - (content_x + 10) * 2,
        header_font,
        24,
    )

    # Рассчитать психоматрицу
    matrix = calculate_psychomatrix(birth_date)

    # Отобразить квадрат 3x3 по центру
    cell_size = 40 * mm  # Увеличил размер для повторений
    matrix_width = 3 * cell_size
    start_x = (page_width - matrix_width) / 2
    start_y = y - 180  # Сместил ниже

    c.setFillColorRGB(*TEXT_MAIN)
    c.setFont(font_bold, 20)

    for row in range(3):
        for col in range(3):
            num = row * 3 + col + 1
            count = matrix.get(num, 0)
            x = start_x + col * cell_size
            y_cell = start_y - row * cell_size
            c.setFillColorRGB(*HEADER_BG)
            c.roundRect(x, y_cell, cell_size, cell_size, 5, fill=1, stroke=0)
            if count > 0:
                c.setFillColorRGB(*YELLOW)
                digits = str(num) * count
                c.drawCentredString(x + cell_size / 2, y_cell + cell_size / 2, digits)
            # Если count == 0, оставляем пустым

    y = start_y - 3 * cell_size - 30  # После квадрата
    c.setFont(font_regular, 12)
    c.setFillColorRGB(*TEXT_MAIN)
    y = _draw_paragraph(c, "Матрица врожденных энергий показывает распределение цифр в дате рождения. Каждая цифра от 1 до 9 повторяется столько раз, сколько она встречается в дате.", content_x + 10, y, page_width - (content_x + 10) * 2, font_regular, 12, 17, 0, 0)

    _draw_footer_links(c, page_width, content_margin, font_regular)


def _draw_innate_energies_page(c: canvas.Canvas, birth_date: date, font_regular: str, font_bold: str, header_font: str) -> None:
    c.showPage()
    content_margin = 14 * mm
    content_padding = 8 * mm
    page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)
    y = top_y - 30

    y = _draw_centered_title(
        c,
        "Врожденные энергии",
        content_x + 10,
        y,
        page_width - (content_x + 10) * 2,
        header_font,
        24,
    )

    matrix = calculate_psychomatrix(birth_date)
    y -= 20

    for energy in matrix_energies:
        num = energy["number"]
        if matrix.get(num, 0) > 0:
            title = energy["title"]
            text = f"{num}: {title}"
            # Разбить текст на строки, если не помещается
            lines = simpleSplit(text, font_bold, 14, page_width - (content_x + 10) * 2 - 40)
            block_height = len(lines) * 18 + 10
            y -= block_height / 2  # Центрировать блок
            # Рисуем блок
            c.setFillColorRGB(*HEADER_BG)
            c.roundRect(content_x + 10, y - block_height / 2, page_width - (content_x + 10) * 2, block_height, 5, fill=1, stroke=0)
            # Рисуем текст центрированно
            c.setFillColorRGB(*YELLOW)
            c.setFont(font_bold, 14)
            for i, line in enumerate(lines):
                c.drawCentredString(page_width / 2, y - 2 - i * 18, line)
            y -= block_height / 2 + 10

    _draw_footer_links(c, page_width, content_margin, font_regular)


def _draw_missing_energies_page(c: canvas.Canvas, birth_date: date, font_regular: str, font_bold: str, header_font: str) -> None:
    c.showPage()
    content_margin = 14 * mm
    content_padding = 8 * mm
    page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)
    y = top_y - 30

    y = _draw_centered_title(
        c,
        "Недостающие энергии",
        content_x + 10,
        y,
        page_width - (content_x + 10) * 2,
        header_font,
        24,
    )
    # Подзаголовок
    c.setFont(font_regular, 16)
    c.setFillColorRGB(*TEXT_MAIN)
    c.drawCentredString(page_width / 2, y - 10, "(нуждаются в проработке)")

    matrix = calculate_psychomatrix(birth_date)
    y -= 20

    for energy in matrix_energies:
        num = energy["number"]
        if matrix.get(num, 0) == 0:
            title = energy["title"]
            text = f"{num}: {title}"
            # Разбить текст на строки, если не помещается
            lines = simpleSplit(text, font_bold, 14, page_width - (content_x + 10) * 2 - 40)
            block_height = len(lines) * 18 + 10
            y -= block_height / 2  # Центрировать блок
            # Рисуем блок
            c.setFillColorRGB(*HEADER_BG)
            c.roundRect(content_x + 10, y - block_height / 2, page_width - (content_x + 10) * 2, block_height, 5, fill=1, stroke=0)
            # Рисуем текст центрированно
            c.setFillColorRGB(*YELLOW)
            c.setFont(font_bold, 14)
            for i, line in enumerate(lines):
                c.drawCentredString(page_width / 2, y - 2 - i * 18, line)
            y -= block_height / 2 + 10

    _draw_footer_links(c, page_width, content_margin, font_regular)


def _draw_missing_energy_details_pages(c: canvas.Canvas, birth_date: date, font_regular: str, font_bold: str, header_font: str) -> None:
    matrix = calculate_psychomatrix(birth_date)

    for energy in matrix_energies:
        num = energy["number"]
        if matrix.get(num, 0) == 0:
            c.showPage()
            content_margin = 14 * mm
            content_padding = 8 * mm
            page_width, page_height, content_x, top_y = _prepare_page_frame(c, content_margin, content_padding)
            y = top_y - 30

            y = _draw_centered_title(
                c,
                f"Число энергии {num}",
                content_x + 10,
                y,
                page_width - (content_x + 10) * 2,
                header_font,
                24,
            )

            description = energy.get("description", "")
            y -= 20
            c.setFont(font_regular, 12)
            c.setFillColorRGB(*TEXT_MAIN)
            y = _draw_paragraph(c, description, content_x + 10, y, page_width - (content_x + 10) * 2, font_regular, 12, 17, 0, 0)

            _draw_footer_links(c, page_width, content_margin, font_regular)


def calculate_psychomatrix(birth_date: date) -> dict[int, int]:
    date_str = birth_date.strftime("%d%m%Y")
    matrix = {i: 0 for i in range(1, 10)}
    for digit in date_str:
        d = int(digit)
        if d != 0:
            matrix[d] += 1
    return matrix


def calculate_consciousness_number(birth_date: date) -> int:
    return reduce_number(birth_date.day)


def calculate_destiny_number(birth_date: date) -> int:
    total = sum(int(d) for d in birth_date.strftime("%d%m%Y"))
    return reduce_number(total)


def calculate_action_number(full_name: str) -> Optional[int]:
    total = 0
    for char in full_name.upper():
        if char in NUMEROLOGY_TABLE:
            total += NUMEROLOGY_TABLE[char]
    if total == 0:
        return None
    return reduce_number(total)


def calculate_character_number(birth_date: date) -> int:
    return reduce_number(birth_date.day)


def calculate_energy_number(birth_date: date) -> int:
    return reduce_number(birth_date.month)




def reduce_number(value: int) -> int:
    if value in (11, 22, 33):
        return value
    while value > 9:
        value = sum(int(d) for d in str(value))
        if value in (11, 22, 33):
            break
    return value


NUMEROLOGY_TABLE = {
    "А": 1, "И": 1, "С": 1, "Ъ": 1,
    "Б": 2, "Й": 2, "Т": 2, "Ы": 2,
    "В": 3, "К": 3, "У": 3, "Ь": 3,
    "Г": 4, "Л": 4, "Ф": 4, "Э": 4,
    "Д": 5, "М": 5, "Х": 5, "Ю": 5,
    "Е": 6, "Н": 6, "Ц": 6, "Я": 6,
    "Ё": 7, "О": 7, "Ч": 7,
    "Ж": 8, "П": 8, "Ш": 8,
    "З": 9, "Р": 9, "Щ": 9,
}
