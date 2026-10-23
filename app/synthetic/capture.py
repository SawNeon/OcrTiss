from __future__ import annotations

import io
import random
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842
DESK_COLORS = ((92, 82, 74), (120, 112, 100), (70, 74, 78))


@dataclass(frozen=True)
class CaptureProfile:
    name: str
    frame_width: int
    frame_height: int
    page_fraction: float
    jpeg_quality: int
    rotation_degrees: float
    blur_radius: float
    printed_from_portal: bool
    perspective: float = 0.0
    shadow: float = 0.0
    edge_crop: float = 0.0


PROFILES = (
    CaptureProfile("phone_far", 1200, 1600, 0.42, 55, 2.0, 1.0, True, perspective=0.03, shadow=0.25),
    CaptureProfile("phone_close", 1200, 1600, 0.78, 70, 0.8, 0.6, True, perspective=0.05, shadow=0.35),
    CaptureProfile("phone_cropped", 1200, 1600, 0.95, 60, 3.0, 0.9, True, perspective=0.07, shadow=0.4, edge_crop=0.06),
    CaptureProfile("scan_good", 2480, 3508, 0.98, 90, 0.2, 0.0, False),
)


def _desk_background(profile: CaptureProfile, rng: random.Random) -> Image.Image:
    base = Image.new("RGB", (profile.frame_width, profile.frame_height), rng.choice(DESK_COLORS))
    noise = Image.effect_noise((profile.frame_width, profile.frame_height), 28).convert("L")
    return Image.composite(base, noise.convert("RGB"), noise.point(lambda value: 200))


def _apply_perspective(page: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    width, height = page.size

    def shift() -> float:
        return rng.uniform(-strength, strength)

    corners = (
        width * shift(), height * shift(),
        width * shift(), height * (1 + shift()),
        width * (1 + shift()), height * (1 + shift()),
        width * (1 + shift()), height * shift(),
    )
    return page.transform((width, height), Image.QUAD, corners, resample=Image.BICUBIC, fillcolor=(250, 249, 245))


def _apply_shadow(page: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    width, height = page.size
    gradient = Image.linear_gradient("L").rotate(rng.uniform(0, 360), resample=Image.BICUBIC).resize((width, height))
    shadow = gradient.point(lambda value: int(255 - value * strength))
    return Image.composite(page, Image.new("RGB", page.size, (40, 40, 40)), shadow)


def _crop_edges(page: Image.Image, fraction: float, rng: random.Random) -> Image.Image:
    width, height = page.size
    left = int(width * rng.uniform(0, fraction))
    top = int(height * rng.uniform(0, fraction))
    return page.crop((left, top, width - int(width * fraction) + left, height - int(height * fraction) + top))


def apply_capture(page: Image.Image, profile: CaptureProfile, seed: int = 0) -> bytes:
    rng = random.Random(seed)
    frame = _desk_background(profile, rng)

    if profile.edge_crop:
        page = _crop_edges(page, profile.edge_crop, rng)

    target_height = int(profile.frame_height * profile.page_fraction)
    scale = target_height / page.height
    scaled_page = page.resize((int(page.width * scale), target_height), Image.LANCZOS)

    if profile.perspective:
        scaled_page = _apply_perspective(scaled_page, profile.perspective, rng)
    if profile.shadow:
        scaled_page = _apply_shadow(scaled_page, profile.shadow, rng)

    if profile.rotation_degrees:
        scaled_page = scaled_page.rotate(
            rng.uniform(-profile.rotation_degrees, profile.rotation_degrees),
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=(250, 249, 245),
        )

    offset = (
        (profile.frame_width - scaled_page.width) // 2 + int(rng.uniform(-20, 20)),
        (profile.frame_height - scaled_page.height) // 2 + int(rng.uniform(-20, 20)),
    )
    frame.paste(scaled_page, offset)

    if profile.blur_radius:
        frame = frame.filter(ImageFilter.GaussianBlur(profile.blur_radius))
    frame = ImageEnhance.Brightness(frame).enhance(rng.uniform(0.92, 1.05))

    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=profile.jpeg_quality)
    return buffer.getvalue()


def wrap_in_pdf(jpeg_bytes: bytes, destination: Path, profile: CaptureProfile, seed: int = 0) -> Path:
    rng = random.Random(seed)
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)

    if profile.printed_from_portal:
        image = pymupdf.Pixmap(io.BytesIO(jpeg_bytes))
        ratio = image.height / image.width
        width = A4_WIDTH_PT - 120
        rect = pymupdf.Rect(60, 200, 60 + width, 200 + width * ratio)
        page.insert_image(rect, stream=jpeg_bytes)

        file_name = f"[AUTOATENDIMENTO_BEN]_{rng.randint(100000, 999999)}_api_{rng.getrandbits(48):012x}.jpeg"
        page.insert_text((40, 30), f"21/09/2026, 14:{rng.randint(10, 59)} {file_name} ({image.width}×{image.height})", fontsize=7)
        page.insert_text((40, A4_HEIGHT_PT - 20), "https://portal.exemplo.com.br/public/outros/upload/09_2026/" + file_name[:48] + "…", fontsize=7)
    else:
        page.insert_image(pymupdf.Rect(0, 0, A4_WIDTH_PT, A4_HEIGHT_PT), stream=jpeg_bytes)

    document.save(destination)
    document.close()
    return destination
