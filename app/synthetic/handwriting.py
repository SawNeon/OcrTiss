from __future__ import annotations

import random
from enum import Enum
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIRS = (
    Path(r"C:\Windows\Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype"),
    Path("/usr/share/fonts"),
)

# Fora do Windows as fontes da Microsoft não existem; a DejaVu cobre o papel da
# Arial para desenhar os rótulos do formulário.
FALLBACKS = ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")
BOLD_FALLBACKS = ("arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")


def find_font(*candidates: str) -> Path | None:
    """Primeira fonte existente entre as candidatas, procurando em todo diretório conhecido."""
    for name in candidates:
        for folder in FONT_DIRS:
            caminho = folder / name
            if caminho.exists():
                return caminho
        for folder in FONT_DIRS:
            if folder.exists():
                achados = sorted(folder.rglob(name))
                if achados:
                    return achados[0]
    return None


class HandStyle(str, Enum):
    TYPED = "typed"
    NEAT = "neat"
    CURSIVE = "cursive"
    RUSHED = "rushed"


class FillMode(str, Enum):
    TYPED_FORM = "typed_form"
    MIXED = "mixed"
    HANDWRITTEN_FORM = "handwritten_form"


STYLE_FONTS: dict[HandStyle, tuple[str, ...]] = {
    HandStyle.TYPED: ("arial.ttf",),
    HandStyle.NEAT: ("Inkfree.ttf", "segoepr.ttf"),
    HandStyle.CURSIVE: ("segoesc.ttf", "BRADHITC.TTF"),
    HandStyle.RUSHED: ("MISTRAL.TTF", "FRSCRIPT.TTF"),
}

STYLE_JITTER: dict[HandStyle, tuple[float, float, float]] = {
    HandStyle.TYPED: (0.0, 0.0, 0.0),
    HandStyle.NEAT: (2.0, 1.5, 0.5),
    HandStyle.CURSIVE: (4.0, 3.0, 1.5),
    HandStyle.RUSHED: (7.0, 5.0, 3.0),
}

STYLE_SIZE_FACTOR: dict[HandStyle, float] = {
    HandStyle.TYPED: 1.0,
    HandStyle.NEAT: 1.05,
    HandStyle.CURSIVE: 1.15,
    HandStyle.RUSHED: 1.3,
}


def load_font(style: HandStyle, size: int, rng: random.Random) -> ImageFont.FreeTypeFont:
    available = [caminho for caminho in (find_font(name) for name in STYLE_FONTS[style]) if caminho]
    if not available:
        regular = find_font(*FALLBACKS)
        return ImageFont.truetype(str(regular), size) if regular else ImageFont.load_default(size)
    chosen = rng.choice(available)
    return ImageFont.truetype(str(chosen), int(size * STYLE_SIZE_FACTOR[style]))


def fit_size(text: str, style: HandStyle, size: int, max_width: int, rng: random.Random) -> int:
    while size > 16:
        font = load_font(style, size, rng)
        if font.getlength(text) <= max_width:
            return size
        size -= 2
    return size


def draw_handwritten(
    canvas: Image.Image,
    text: str,
    left: int,
    baseline: int,
    style: HandStyle,
    size: int,
    rng: random.Random,
    max_width: int | None = None,
    ink: tuple[int, int, int] = (20, 30, 90),
) -> None:
    """Draws text word by word with jitter, so it does not look like a clean font line."""
    if max_width:
        size = fit_size(text, style, size, max_width, rng)

    if style is HandStyle.TYPED:
        font = load_font(style, size, rng)
        ImageDraw.Draw(canvas).text((left, baseline - size), text, font=font, fill=(15, 15, 15))
        return

    baseline_jitter, slant_jitter, spacing_jitter = STYLE_JITTER[style]
    cursor = left

    for word in text.split(" "):
        if not word:
            cursor += int(size * 0.4)
            continue

        font = load_font(style, size, rng)
        box = font.getbbox(word)
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= 0 or height <= 0:
            continue

        tile = Image.new("RGBA", (width + size, height + size), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((size // 2, size // 2 - box[1]), word, font=font, fill=(*ink, 255))
        tile = tile.rotate(rng.uniform(-slant_jitter, slant_jitter), resample=Image.BICUBIC, expand=True)

        offset_y = int(rng.uniform(-baseline_jitter, baseline_jitter))
        canvas.paste(tile, (int(cursor), baseline - int(size * 1.4) + offset_y), tile)
        cursor += width + int(size * 0.28) + int(rng.uniform(-spacing_jitter, spacing_jitter))
