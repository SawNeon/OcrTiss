from __future__ import annotations

from app.recognition import decoder
from app.recognition.character_classifier import BLANK_LABEL, Prediction


class FakeClassifier:
    """Stands in for the model: returns the candidates the test wants to decode."""

    def __init__(self, ranked):
        self._ranked = ranked

    def predict_topk(self, cells, k=3):
        return self._ranked


def test_date_validator_rejects_impossible_day():
    assert decoder.is_valid_date("10082026")
    assert not decoder.is_valid_date("32082026")
    assert not decoder.is_valid_date("1008202")


def test_decoder_prefers_the_candidate_that_satisfies_the_rule():
    ranked = [
        [Prediction("3", 0.6), Prediction("1", 0.4)],
        [Prediction("2", 0.9), Prediction("0", 0.1)],
        [Prediction("1", 0.9), Prediction("0", 0.1)],
        [Prediction("0", 0.9), Prediction("8", 0.1)],
        [Prediction("2", 0.9), Prediction("0", 0.1)],
        [Prediction("0", 0.9), Prediction("0", 0.1)],
        [Prediction("2", 0.9), Prediction("0", 0.1)],
        [Prediction("6", 0.9), Prediction("0", 0.1)],
    ]
    decoded = decoder.decode_field(FakeClassifier(ranked), "request_date", [None] * 8)

    assert decoded.value == "12102026"
    assert decoded.validated is True


def test_field_without_rule_is_not_marked_invalid():
    ranked = [[Prediction("7", 0.9)], [Prediction("4", 0.8)]]
    decoded = decoder.decode_field(FakeClassifier(ranked), "campo_sem_regra", [None, None])

    assert decoded.value == "74"
    assert decoded.validated is None


def test_blank_cells_produce_no_value():
    ranked = [[Prediction(BLANK_LABEL, 1.0)], [Prediction(BLANK_LABEL, 1.0)]]
    decoded = decoder.decode_field(FakeClassifier(ranked), "cbo_code", [None, None])

    assert decoded.value == ""


def test_catalogue_restricts_accepted_codes():
    decoder.register_catalogue("procedure9_code", {"40304361"})
    ranked = [
        [Prediction("4", 0.9)], [Prediction("0", 0.9)], [Prediction("3", 0.9)], [Prediction("0", 0.9)],
        [Prediction("4", 0.9)], [Prediction("3", 0.9)], [Prediction("6", 0.9)],
        [Prediction("7", 0.6), Prediction("1", 0.5)],
    ]
    decoded = decoder.decode_field(FakeClassifier(ranked), "procedure9_code", [None] * 8)

    assert decoded.value == "40304361"
    assert decoded.validated is True
