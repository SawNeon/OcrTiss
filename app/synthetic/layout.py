from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

SCALE = 3
REFERENCE_WIDTH = 827
REFERENCE_HEIGHT = 1170
A4_WIDTH_PX = REFERENCE_WIDTH * SCALE
A4_HEIGHT_PX = REFERENCE_HEIGHT * SCALE

FORM_TITLE = ("GUIA DE SOLICITAÇÃO", "DE INTERNAÇÃO")
OPERATOR_NAME = "VALE SAÚDE"
OPERATOR_UNIT = "Cooperativa"


class ValueKind(str, Enum):
    DIGITS = "digits"
    TEXT = "text"
    DATE = "date"
    CODE = "code"


@dataclass(frozen=True)
class FormField:
    name: str
    number: str
    label: str
    left: int
    top: int
    width: int
    cells: int | None = None
    kind: ValueKind = ValueKind.DIGITS
    handwritten: bool = False
    height: int = 24


@dataclass(frozen=True)
class SectionBar:
    label: str
    top: int


BORDER = (18, 68, 775, 1105)
LOGO_BOX = (25, 88, 92, 118)
TITLE_CENTER = 360
GUIDE_NUMBER_LABEL = (448, 96)
GUIDE_NUMBER_VALUE = (520, 88)

SECTIONS = [
    SectionBar("Dados do Beneficiário", 214),
    SectionBar("Dados do Contratado Solicitante", 296),
    SectionBar("Dados do Hospital /Local Solicitado / Dados da Internação", 392),
    SectionBar("Procedimentos ou Itens Assistenciais Solicitados", 646),
    SectionBar("Dados da Autorização", 900),
]

FIELDS = [
    FormField("ans_registration", "1", "Registro ANS", 22, 140, 78, cells=6),
    FormField("operator_guide_number", "3", "Número da Guia Atribuído pela Operadora", 105, 140, 385, cells=20),
    FormField("authorization_date", "4", "Data da Autorização", 22, 176, 180, cells=8, kind=ValueKind.DATE),
    FormField("password", "5", "Senha", 205, 176, 365, cells=20),
    FormField("password_expiry_date", "6", "Data de Validade da Senha", 575, 176, 180, cells=8, kind=ValueKind.DATE),

    FormField("member_card_number", "7", "Número da Carteira", 22, 230, 370, cells=17, handwritten=True),
    FormField("card_expiry_date", "8", "Validade da Carteira", 400, 230, 160, cells=8, kind=ValueKind.DATE, handwritten=True),
    FormField("newborn_care", "9", "Atendimento a RN", 566, 230, 80, cells=1, kind=ValueKind.CODE, handwritten=True),
    FormField("member_name", "10", "Nome", 22, 266, 470, kind=ValueKind.TEXT, height=28),
    FormField("national_health_card", "11", "Cartão Nacional de Saúde", 500, 266, 255, cells=15),

    FormField("requester_operator_code", "12", "Código na Operadora", 22, 306, 260, cells=13),
    FormField("requester_provider_name", "13", "Nome do Contratado", 290, 306, 465, kind=ValueKind.TEXT),
    FormField("requesting_professional_name", "14", "Nome do Profissional Solicitante", 22, 352, 300, kind=ValueKind.TEXT, handwritten=True, height=30),
    FormField("professional_council", "15", "Conselho Profissional", 328, 352, 68, kind=ValueKind.CODE, handwritten=True, height=30),
    FormField("council_number", "16", "Número no Conselho", 400, 352, 225, cells=12, handwritten=True, height=30),
    FormField("council_state", "17", "UF", 630, 352, 42, cells=2, kind=ValueKind.CODE, handwritten=True, height=30),
    FormField("cbo_code", "18", "Código CBO", 676, 352, 79, cells=6, handwritten=True, height=30),

    FormField("hospital_operator_code", "19", "Código na Operadora / CNPJ", 22, 402, 260, cells=14),
    FormField("hospital_name", "20", "Nome do Hospital/Local Solicitado", 290, 402, 325, kind=ValueKind.TEXT),
    FormField("suggested_admission_date", "21", "Data sugerida para internação", 620, 402, 135, cells=8, kind=ValueKind.DATE),
    FormField("care_type", "22", "Caráter do Atendimento", 22, 438, 120, cells=1, kind=ValueKind.CODE, handwritten=True),
    FormField("admission_type", "23", "Tipo de Internação", 146, 438, 95, cells=1, kind=ValueKind.CODE, handwritten=True),
    FormField("admission_regime", "24", "Regime de Internação", 245, 438, 100, cells=1, kind=ValueKind.CODE, handwritten=True),
    FormField("requested_daily_rates", "25", "Qtde. Diárias Solicitadas", 349, 438, 105, cells=3, handwritten=True),
    FormField("opme_forecast", "26", "Previsão de uso de OPME", 458, 438, 110, cells=1, kind=ValueKind.CODE, handwritten=True),
    FormField("chemotherapy_forecast", "27", "Previsão de uso de quimioterápico", 572, 438, 183, cells=1, kind=ValueKind.CODE, handwritten=True),

    FormField("clinical_indication", "28", "Indicação Clínica", 22, 470, 733, kind=ValueKind.TEXT, height=145, handwritten=True),

    FormField("main_icd10", "29", "CID 10 Principal", 22, 616, 110, cells=5, kind=ValueKind.CODE, handwritten=True),
    FormField("icd10_2", "30", "CID 10 (2)", 136, 616, 110, cells=5, kind=ValueKind.CODE),
    FormField("icd10_3", "31", "CID 10 (3)", 250, 616, 110, cells=5, kind=ValueKind.CODE),
    FormField("icd10_4", "32", "CID 10 (4)", 364, 616, 110, cells=5, kind=ValueKind.CODE),
    FormField("accident_indication", "33", "Indicação de Acidente (acidente ou doença relacionada)", 478, 616, 277, cells=1, kind=ValueKind.CODE),

    FormField("authorized_admission_date", "39", "Data Provável da Admissão Hospitalar", 22, 908, 190, cells=8, kind=ValueKind.DATE),
    FormField("authorized_daily_rates", "40", "Qtde. Diárias Autorizadas", 216, 908, 110, cells=3),
    FormField("accommodation_type", "41", "Tipo da Acomodação Autorizada", 330, 908, 175, cells=1, kind=ValueKind.CODE),
    FormField("authorized_operator_code", "42", "Código na Operadora / CNPJ autorizado", 22, 946, 260, cells=14),
    FormField("authorized_hospital_name", "43", "Nome do Hospital / Local Autorizado", 290, 946, 365, kind=ValueKind.TEXT),
    FormField("cnes_code", "44", "Código CNES", 660, 946, 95, cells=7),
    FormField("notes", "45", "Observação / Justificativa", 22, 984, 733, kind=ValueKind.TEXT, height=60),
    FormField("request_date", "46", "Data da Solicitação", 22, 1048, 170, cells=8, kind=ValueKind.DATE, handwritten=True, height=50),
]

SIGNATURE_BOXES = [
    ("47", "Assinatura do Profissional Solicitante", 196, 1048, 205, 50),
    ("48", "Assinatura do Beneficiário ou Responsável", 405, 1048, 175, 50),
    ("49", "Assinatura do Responsável pela Autorização", 584, 1048, 171, 50),
]

SHEET_LEFT = BORDER[0] - 10
SHEET_TOP = BORDER[1] - 12
SHEET_WIDTH = (BORDER[2] + 10) - SHEET_LEFT
SHEET_HEIGHT = (BORDER[3] + 14) - SHEET_TOP

COMB_BASELINE_OFFSET = 20
COMB_CELL_TOP_OFFSET = 13
COMB_CELL_BOTTOM_OFFSET = 2


def sheet_rect(left: float, top: float, width: float, height: float) -> tuple[int, int, int, int]:
    """Field rectangle in the cropped-sheet coordinate system, in pixels."""
    return (
        int((left - SHEET_LEFT) * SCALE),
        int((top - SHEET_TOP) * SCALE),
        int((left - SHEET_LEFT + width) * SCALE),
        int((top - SHEET_TOP + height) * SCALE),
    )


def comb_cells(field: FormField) -> list[tuple[int, int, int, int]]:
    """One rectangle per character cell, already in sheet pixels."""
    if not field.cells:
        return []

    left = (field.left - SHEET_LEFT) * SCALE + 6
    width = field.width * SCALE - 12
    cell_width = width / field.cells
    baseline = (field.top - SHEET_TOP + COMB_BASELINE_OFFSET) * SCALE

    return [
        (
            int(left + index * cell_width),
            int(baseline - COMB_CELL_TOP_OFFSET * SCALE),
            int(left + (index + 1) * cell_width),
            int(baseline + COMB_CELL_BOTTOM_OFFSET * SCALE),
        )
        for index in range(field.cells)
    ]


PROCEDURE_TABLE_TOP = 656
PROCEDURE_ROW_HEIGHT = 18.2
PROCEDURE_ROWS = 12
PROCEDURE_ROW_OFFSET = 16
PROCEDURE_BASELINE_OFFSET = 2
PROCEDURE_COLUMNS = {
    "table": (34, "Tabela", 34, 34, 4),
    "code": (35, "Código do Procedimento ou\nItem Assistencial", 72, 166, 10),
    "description": (36, "Descrição", 244, 340, None),
    "requested_quantity": (37, "Qtde Solic", 600, 62, 3),
    "authorized_quantity": (38, "Qtde Aut", 676, 62, 3),
}


def procedure_comb_cells(row: int, column: str) -> list[tuple[int, int, int, int]]:
    """Character cells of one procedure row, in sheet pixels."""
    _, _, left, width, cells = PROCEDURE_COLUMNS[column]
    if not cells:
        return []

    baseline = (
        (PROCEDURE_TABLE_TOP + PROCEDURE_ROW_OFFSET + PROCEDURE_BASELINE_OFFSET - SHEET_TOP) * SCALE
        + row * PROCEDURE_ROW_HEIGHT * SCALE
    )
    origin = (left - SHEET_LEFT) * SCALE
    cell_width = width * SCALE / cells

    return [
        (
            int(origin + index * cell_width),
            int(baseline - COMB_CELL_TOP_OFFSET * SCALE),
            int(origin + (index + 1) * cell_width),
            int(baseline + COMB_CELL_BOTTOM_OFFSET * SCALE),
        )
        for index in range(cells)
    ]


def procedure_description_rect(row: int) -> tuple[int, int, int, int]:
    _, _, left, width, _ = PROCEDURE_COLUMNS["description"]
    baseline = (
        (PROCEDURE_TABLE_TOP + PROCEDURE_ROW_OFFSET - SHEET_TOP) * SCALE + row * PROCEDURE_ROW_HEIGHT * SCALE
    )
    return (
        int((left - SHEET_LEFT) * SCALE),
        int(baseline - 12 * SCALE),
        int((left - SHEET_LEFT + width) * SCALE),
        int(baseline + 10 * SCALE),
    )
