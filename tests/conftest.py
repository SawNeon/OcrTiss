from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.synthetic.capture import PROFILES, apply_capture, wrap_in_pdf
from app.synthetic.guide_generator import generate_guide
from app.synthetic.handwriting import FillMode, HandStyle

SCAN = next(profile for profile in PROFILES if profile.name == "scan_good")


@pytest.fixture(scope="session")
def synthetic_guide():
    return generate_guide("test", HandStyle.NEAT, seed=4242, fill_mode=FillMode.MIXED)


@pytest.fixture(scope="session")
def guide_pdf(synthetic_guide, tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("guides")
    destination = folder / "guia.pdf"
    wrap_in_pdf(apply_capture(synthetic_guide.image, SCAN, seed=1), destination, SCAN, seed=1)
    return destination


@pytest.fixture(scope="session")
def guide_png(synthetic_guide, tmp_path_factory) -> Path:
    import cv2
    import numpy as np

    folder = tmp_path_factory.mktemp("images")
    destination = folder / "guia.png"
    array = cv2.cvtColor(np.array(synthetic_guide.image), cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(destination), array)
    return destination
