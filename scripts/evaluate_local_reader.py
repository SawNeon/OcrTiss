"""Scores the local (no-API) reading of coded fields against the dataset ground truth.

Usage:
    python scripts/evaluate_local_reader.py DATASET [--profile scan_good] [--no-validation]

Reports exact matches, character accuracy and — the number that matters for an
automated flow — how often a value that passed domain validation was right.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.extraction.template_reader import read_coded_fields
from app.recognition import decoder
from app.synthetic.guide_generator import PROCEDURE_CATALOG
from app.synthetic.layout import FIELDS, PROCEDURE_COLUMNS

PROCEDURE_ROWS = 3


def coded_field_names() -> set[str]:
    names = {form_field.name for form_field in FIELDS if form_field.cells}
    for row in range(1, PROCEDURE_ROWS + 1):
        names.update(f"procedure{row}_{column}" for column, spec in PROCEDURE_COLUMNS.items() if spec[4])
    return names


def register_catalogues() -> None:
    codes = {code for code, _ in PROCEDURE_CATALOG}
    for row in range(1, PROCEDURE_ROWS + 1):
        decoder.register_catalogue(f"procedure{row}_code", codes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--profile", default="scan_good")
    parser.add_argument("--no-validation", action="store_true")
    args = parser.parse_args()

    if args.no_validation:
        decoder.VALIDATORS.clear()
    else:
        register_catalogues()

    settings = get_settings()
    coded = coded_field_names()
    tally = defaultdict(int)
    characters = [0, 0]
    elapsed = 0.0
    mistakes: list[str] = []

    for pdf_path in sorted(args.folder.glob(f"*__{args.profile}.pdf")):
        identifier = pdf_path.stem.split("__")[0]
        truth = json.loads((args.folder / f"{identifier}.json").read_text(encoding="utf-8"))["fields"]

        started = time.perf_counter()
        reading = read_coded_fields(pdf_path, 1, settings)
        elapsed += time.perf_counter() - started

        expected_values = {
            name: "".join(character for character in value if character.isalnum())
            for name, value in truth.items()
            if value and name in coded
        }

        for name, expected in expected_values.items():
            found = reading.values.get(name, "")
            characters[1] += max(len(expected), len(found))
            characters[0] += sum(a == b for a, b in zip(found, expected, strict=False))

            if found == expected:
                tally["exact"] += 1
                if reading.validated.get(name):
                    tally["exact_and_validated"] += 1
            elif not found:
                tally["unread"] += 1
            else:
                tally["wrong"] += 1
                if reading.validated.get(name):
                    tally["wrong_but_validated"] += 1
                if len(mistakes) < 8:
                    mistakes.append(f"  {name:<28} {expected:<19} -> {found}")

        for name in reading.values:
            if name in coded and not expected_values.get(name):
                tally["fabricated"] += 1

    total = tally["exact"] + tally["wrong"] + tally["unread"]
    validated = tally["exact_and_validated"] + tally["wrong_but_validated"]
    if not total:
        print("nothing to score")
        return

    print(f"perfil {args.profile} | validacao de dominio: {'off' if args.no_validation else 'on'}")
    print(f"campos codificados preenchidos: {total}")
    print(f"  exatos            {tally['exact']:>3}  ({tally['exact'] / total:.0%})")
    print(f"  errados           {tally['wrong']:>3}")
    print(f"  nao lidos         {tally['unread']:>3}")
    print(f"  inventados        {tally['fabricated']:>3}  (campo em branco preenchido)")
    print(f"  caracteres        {characters[0]}/{characters[1]} = {characters[0] / characters[1]:.0%}")
    if validated:
        print(
            f"  passaram na validacao: {validated}, destes {tally['exact_and_validated']} corretos "
            f"({tally['exact_and_validated'] / validated:.0%})"
        )
    print(f"  tempo medio por pagina: {elapsed / max(1, len(list(args.folder.glob(f'*__{args.profile}.pdf')))):.1f}s")
    if mistakes:
        print("exemplos de erro:")
        print("\n".join(mistakes))


if __name__ == "__main__":
    main()
