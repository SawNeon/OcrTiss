from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.synthetic.handwriting import FillMode, HandStyle, draw_handwritten
from app.synthetic.layout import (
    A4_HEIGHT_PX,
    A4_WIDTH_PX,
    BORDER,
    FIELDS,
    FORM_TITLE,
    GUIDE_NUMBER_LABEL,
    GUIDE_NUMBER_VALUE,
    LOGO_BOX,
    OPERATOR_NAME,
    OPERATOR_UNIT,
    PROCEDURE_COLUMNS,
    PROCEDURE_ROW_HEIGHT,
    PROCEDURE_ROWS,
    PROCEDURE_TABLE_TOP,
    SCALE,
    SECTIONS,
    SIGNATURE_BOXES,
    TITLE_CENTER,
)

FORM_INK = (22, 104, 84)
LABEL_INK = (35, 45, 42)
TYPED_INK = (25, 25, 28)
PEN_INK = (28, 38, 110)
PAPER = (252, 252, 249)

ARIAL = r"C:\Windows\Fonts\arial.ttf"
ARIAL_BOLD = r"C:\Windows\Fonts\arialbd.ttf"

DOCTORS = [
    {"name": "BRUNO CASTELO LIMA", "council_number": "52914", "state": "MG", "cbo": "225265"},
    {"name": "HELENA MARQUES DUTRA", "council_number": "51284", "state": "MG", "cbo": "225125"},
    {"name": "RAFAEL PIMENTA LOBO", "council_number": "27419", "state": "SP", "cbo": "225103"},
    {"name": "PATRICIA GUIMARAES SOLER", "council_number": "58472", "state": "MG", "cbo": "223605"},
    {"name": "EDUARDO NASCIMENTO PRADO", "council_number": "19758", "state": "RJ", "cbo": "225250"},
    {"name": "TATIANE REZENDE CAMPOS", "council_number": "72641", "state": "MG", "cbo": "225135"},
]

MEMBERS = [
    "ANDREIA SIQUEIRA RAMOS", "BRUNO TEIXEIRA NOGUEIRA", "CARLA ESTEVES MACHADO",
    "DANIEL FONSECA BARBOSA", "ELIANE CARVALHO DIAS", "FABIO GONCALVES PEREIRA",
    "GISELE ALMEIDA RAMOS", "JOAQUIM OLIVEIRA MENDES", "LUCIANA PIRES SOARES",
    "MARCELO ANTUNES FARIA",
]

HOSPITALS = [
    "HOSPITAL SANTA CLARA DE VARGINHA",
    "CLINICA SAO BENEDITO LTDA",
    "HOSPITAL REGIONAL DO SUL DE MINAS",
]

PROCEDURE_CATALOG = [
    ("31403336", "RIZOTOMIA"),
    ("20103301", "BLOQUEIO MIOFASCIAL"),
    ("40808041", "RESSONANCIA MAGNETICA DE CRANIO"),
    ("31602096", "ARTRODESE DE COLUNA LOMBAR"),
    ("40304361", "TRATAMENTO OCULAR QUIMIOTERAPICO"),
    ("30731131", "COLECISTECTOMIA VIDEOLAPAROSCOPICA"),
    ("40901165", "ULTRASSONOGRAFIA ABDOMEN TOTAL"),
]

INDICATIONS = [
    "PACIENTE ACIMA COM DOR CERVICAL, SEM MELHORA AO TRATAMENTO CLINICO E MEDICAMENTOSO. SUBMETIDO A BLOQUEIO DE TESTE COM RESPOSTA POSITIVO.",
    "PACIENTE COM LOMBALGIA CRONICA HA 2 ANOS, REFRATARIA A FISIOTERAPIA E MEDICACAO. INDICADO PROCEDIMENTO CONFORME EXAMES EM ANEXO.",
    "QUADRO DE CEFALEIA PERSISTENTE COM PIORA PROGRESSIVA. SOLICITO EXAME DE IMAGEM PARA INVESTIGACAO DIAGNOSTICA.",
    "PACIENTE COM COLELITIASE SINTOMATICA, EPISODIOS RECORRENTES DE DOR EM HIPOCONDRIO DIREITO. INDICADA CIRURGIA.",
]

ICD10 = ["M545", "M541", "G442", "K802", "H358"]


@dataclass
class SyntheticGuide:
    identifier: str
    doctor_style: HandStyle
    fill_mode: FillMode
    image: Image.Image
    ground_truth: dict[str, str] = field(default_factory=dict)
    doctor: dict[str, str] = field(default_factory=dict)


def _scaled(value: float) -> int:
    return int(value * SCALE)


def _date(rng: random.Random) -> str:
    return f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/2026"


def _digits(rng: random.Random, count: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(count))


def _build_content(rng: random.Random) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
    doctor = rng.choice(DOCTORS)
    procedures = [
        {"table": "22", "code": code, "description": description, "requested_quantity": f"{rng.randint(1, 6):02d}"}
        for code, description in rng.sample(PROCEDURE_CATALOG, rng.randint(1, 3))
    ]

    values = {name: "" for name in (item.name for item in FIELDS)}
    values.update(
        {
            "ans_registration": _digits(rng, 6),
            "member_name": rng.choice(MEMBERS),
            "member_card_number": _digits(rng, 17),
            "requesting_professional_name": doctor["name"],
            "professional_council": "CRM",
            "council_number": doctor["council_number"],
            "council_state": doctor["state"],
            "cbo_code": doctor["cbo"],
            "hospital_name": rng.choice(HOSPITALS),
            "care_type": rng.choice(["E", "U"]),
            "admission_type": str(rng.randint(1, 4)),
            "requested_daily_rates": f"{rng.randint(1, 9):02d}",
            "clinical_indication": rng.choice(INDICATIONS),
            "main_icd10": rng.choice(ICD10),
            "request_date": _date(rng),
        }
    )
    return values, doctor, procedures


def _draw_comb(draw: ImageDraw.ImageDraw, left: int, top: int, width: int, cells: int) -> list[tuple[int, int]]:
    cell_width = width / cells
    positions = []
    baseline = top + _scaled(11)
    for index in range(cells):
        x0 = left + int(index * cell_width)
        draw.line([x0, baseline - _scaled(7), x0, baseline], fill=FORM_INK, width=2)
        draw.line([x0, baseline, x0 + int(cell_width), baseline], fill=FORM_INK, width=2)
        positions.append((x0, baseline))
    draw.line(
        [left + width, baseline - _scaled(7), left + width, baseline], fill=FORM_INK, width=2
    )
    return positions


def _draw_field_frame(draw: ImageDraw.ImageDraw, field_box, label_font) -> None:
    left, top = _scaled(field_box.left), _scaled(field_box.top)
    width, height = _scaled(field_box.width), _scaled(field_box.height)
    draw.rectangle([left, top, left + width, top + height], outline=FORM_INK, width=2)
    draw.text((left + 6, top + 4), f"{field_box.number} - {field_box.label}", font=label_font, fill=LABEL_INK)


def _fill_comb(draw: ImageDraw.ImageDraw, positions, value: str, font, style: HandStyle, canvas, rng) -> None:
    """Separators are printed on the form, so only the characters go in the cells."""
    for character, (x0, baseline) in zip("".join(c for c in value if c.isalnum()), positions, strict=False):
        if style is HandStyle.TYPED:
            draw.text((x0 + 8, baseline - _scaled(8)), character, font=font, fill=TYPED_INK)
        else:
            draw_handwritten(canvas, character, x0 + 6, baseline - 4, style, _scaled(8), rng)


def _field_style(field_box, doctor_style: HandStyle, fill_mode: FillMode) -> HandStyle:
    if fill_mode is FillMode.TYPED_FORM:
        return HandStyle.TYPED
    if fill_mode is FillMode.HANDWRITTEN_FORM:
        return doctor_style
    return doctor_style if field_box.handwritten else HandStyle.TYPED


def generate_guide(
    identifier: str,
    doctor_style: HandStyle,
    seed: int,
    fill_mode: FillMode = FillMode.MIXED,
    blank: bool = False,
) -> SyntheticGuide:
    rng = random.Random(seed)
    values, doctor, procedures = _build_content(rng)
    if blank:
        values = {name: "" for name in values}
        procedures = []

    canvas = Image.new("RGB", (A4_WIDTH_PX, A4_HEIGHT_PX), PAPER)
    draw = ImageDraw.Draw(canvas)

    label_font = ImageFont.truetype(ARIAL, _scaled(5))
    section_font = ImageFont.truetype(ARIAL_BOLD, _scaled(6))
    title_font = ImageFont.truetype(ARIAL_BOLD, _scaled(13))
    typed_font = ImageFont.truetype(ARIAL, _scaled(9))
    comb_font = ImageFont.truetype(ARIAL, _scaled(9))
    number_font = ImageFont.truetype(ARIAL, _scaled(15))

    draw.rectangle([_scaled(BORDER[0]), _scaled(BORDER[1]), _scaled(BORDER[2]), _scaled(BORDER[3])], outline=FORM_INK, width=3)

    draw.rectangle([_scaled(LOGO_BOX[0]), _scaled(LOGO_BOX[1]), _scaled(LOGO_BOX[2]), _scaled(LOGO_BOX[3])], fill=FORM_INK)
    draw.text((_scaled(LOGO_BOX[0]) + 10, _scaled(LOGO_BOX[1]) + 12), OPERATOR_NAME, font=ImageFont.truetype(ARIAL_BOLD, _scaled(7)), fill=(255, 255, 255))
    draw.text((_scaled(LOGO_BOX[0]) + 10, _scaled(LOGO_BOX[3]) + 4), OPERATOR_UNIT, font=label_font, fill=LABEL_INK)

    for index, line in enumerate(FORM_TITLE):
        text_width = draw.textlength(line, font=title_font)
        draw.text((_scaled(TITLE_CENTER) - text_width / 2, _scaled(92) + index * _scaled(16)), line, font=title_font, fill=TYPED_INK)

    draw.text((_scaled(GUIDE_NUMBER_LABEL[0]), _scaled(GUIDE_NUMBER_LABEL[1])), "2- Nº Guia no Prestador", font=label_font, fill=LABEL_INK)
    guide_number = _digits(rng, 6)
    if not blank:
        draw.text((_scaled(GUIDE_NUMBER_VALUE[0]), _scaled(GUIDE_NUMBER_VALUE[1])), f"Nº  {guide_number}", font=number_font, fill=TYPED_INK)
        values["provider_guide_number"] = guide_number

    for section in SECTIONS:
        top = _scaled(section.top)
        draw.rectangle([_scaled(BORDER[0]) + 4, top, _scaled(BORDER[2]) - 4, top + _scaled(9)], fill=(226, 236, 232))
        draw.text((_scaled(BORDER[0]) + 12, top + 2), section.label, font=section_font, fill=LABEL_INK)

    for field_box in FIELDS:
        _draw_field_frame(draw, field_box, label_font)
        value = values.get(field_box.name, "")
        style = _field_style(field_box, doctor_style, fill_mode)

        if field_box.cells:
            positions = _draw_comb(
                draw, _scaled(field_box.left) + 6, _scaled(field_box.top) + _scaled(9), _scaled(field_box.width) - 12, field_box.cells
            )
            if value:
                _fill_comb(draw, positions, value, comb_font, style, canvas, rng)
        elif value:
            top = _scaled(field_box.top) + _scaled(field_box.height) - 8
            if field_box.name == "clinical_indication":
                _draw_paragraph(canvas, draw, value, field_box, style, typed_font, rng)
            elif style is HandStyle.TYPED:
                draw.text((_scaled(field_box.left) + 14, top - _scaled(11)), value, font=typed_font, fill=TYPED_INK)
            else:
                draw_handwritten(
                    canvas, value, _scaled(field_box.left) + 14, top, style, _scaled(10), rng,
                    max_width=_scaled(field_box.width) - 28, ink=PEN_INK,
                )

    procedure_style = HandStyle.TYPED if fill_mode is FillMode.TYPED_FORM else doctor_style
    _draw_procedure_table(canvas, draw, procedures, procedure_style, label_font, comb_font, rng)
    _draw_signature_area(canvas, draw, doctor, label_font, rng, blank=blank)

    for index, procedure in enumerate(procedures, start=1):
        for key, value in procedure.items():
            values[f"procedure{index}_{key}"] = value

    sheet = canvas.crop(
        (_scaled(BORDER[0] - 10), _scaled(BORDER[1] - 12), _scaled(BORDER[2] + 10), _scaled(BORDER[3] + 14))
    )
    return SyntheticGuide(identifier, doctor_style, fill_mode, sheet, values, doctor)


def _draw_paragraph(canvas, draw, text: str, field_box, style: HandStyle, typed_font, rng) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    max_chars = 62 if style is HandStyle.TYPED else 46

    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)

    top = _scaled(field_box.top) + _scaled(20)
    for index, line in enumerate(lines[:4]):
        baseline = top + index * _scaled(13)
        if style is HandStyle.TYPED:
            draw.text((_scaled(field_box.left) + 20, baseline), line, font=typed_font, fill=TYPED_INK)
        else:
            draw_handwritten(
                canvas, line, _scaled(field_box.left) + 20, baseline + _scaled(9), style, _scaled(10), rng,
                max_width=_scaled(field_box.width) - 40, ink=PEN_INK,
            )


def _draw_procedure_table(canvas, draw, procedures, style, label_font, comb_font, rng) -> None:
    top = _scaled(PROCEDURE_TABLE_TOP)
    draw.rectangle([_scaled(BORDER[0]) + 4, top, _scaled(BORDER[2]) - 4, _scaled(896)], outline=FORM_INK, width=2)

    for _, (number, label, left, _width, _cells) in PROCEDURE_COLUMNS.items():
        for offset, line in enumerate(label.split("\n")):
            draw.text((_scaled(left), top + 6 + offset * _scaled(6)), f"{number}-{line}" if offset == 0 else line, font=label_font, fill=LABEL_INK)

    row_font = ImageFont.truetype(ARIAL, _scaled(6))

    for row in range(PROCEDURE_ROWS):
        row_top = top + _scaled(16) + int(row * PROCEDURE_ROW_HEIGHT * SCALE)
        draw.text((_scaled(24), row_top), f"{row + 1:02d}-", font=label_font, fill=LABEL_INK)
        procedure = procedures[row] if row < len(procedures) else None

        for key, (_, _, left, width, cells) in PROCEDURE_COLUMNS.items():
            if not cells:
                draw.line(
                    [_scaled(left), row_top + _scaled(9), _scaled(left + width), row_top + _scaled(9)],
                    fill=FORM_INK, width=1,
                )
                if procedure:
                    draw_handwritten(
                        canvas, procedure.get(key, ""), _scaled(left) + 10, row_top + _scaled(8), style, _scaled(8), rng,
                        max_width=_scaled(width) - 20, ink=PEN_INK,
                    )
                continue

            positions = _draw_comb(draw, _scaled(left), row_top - _scaled(9), _scaled(width), cells)
            if procedure:
                _fill_comb(draw, positions, procedure.get(key, ""), row_font, style, canvas, rng)


def _draw_signature_area(canvas, draw, doctor, label_font, rng, blank: bool = False) -> None:
    for number, label, left, top, width, height in SIGNATURE_BOXES:
        draw.rectangle(
            [_scaled(left), _scaled(top), _scaled(left + width), _scaled(top + height)], outline=FORM_INK, width=2
        )
        draw.text((_scaled(left) + 6, _scaled(top) + 4), f"{number}-{label}", font=label_font, fill=LABEL_INK)

    if blank:
        return

    base_left, base_top = _scaled(SIGNATURE_BOXES[0][2]) + 40, _scaled(SIGNATURE_BOXES[0][3]) + _scaled(30)
    draw_handwritten(canvas, doctor["name"].split()[0].title(), base_left, base_top, HandStyle.RUSHED, _scaled(11), rng, ink=PEN_INK)

    stamp = Image.new("RGBA", (_scaled(120), _scaled(40)), (0, 0, 0, 0))
    stamp_draw = ImageDraw.Draw(stamp)
    stamp_font = ImageFont.truetype(ARIAL_BOLD, _scaled(6))
    stamp_draw.rectangle([0, 0, _scaled(120) - 2, _scaled(40) - 2], outline=(70, 80, 160), width=2)
    stamp_draw.text((10, 8), f"Dr(a). {doctor['name'].title()}", font=stamp_font, fill=(70, 80, 160))
    stamp_draw.text((10, 8 + _scaled(9)), f"CRM {doctor['state']} {doctor['council_number']}", font=stamp_font, fill=(70, 80, 160))
    stamp_draw.text((10, 8 + _scaled(18)), f"CBO {doctor['cbo']}", font=stamp_font, fill=(70, 80, 160))
    stamp = stamp.rotate(rng.uniform(-7, 7), resample=Image.BICUBIC, expand=True)
    canvas.paste(stamp, (base_left - _scaled(14), base_top + _scaled(2)), stamp)


def save_ground_truth(guide: SyntheticGuide, folder: Path) -> Path:
    path = folder / f"{guide.identifier}.json"
    payload = {
        "identifier": guide.identifier,
        "doctor_style": guide.doctor_style.value,
        "fill_mode": guide.fill_mode.value,
        "doctor": guide.doctor,
        "fields": guide.ground_truth,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@lru_cache(maxsize=1)
def blank_form_image() -> Image.Image:
    """Empty form, used as the alignment template."""
    return generate_guide("template", HandStyle.TYPED, seed=0, blank=True).image
