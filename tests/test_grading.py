from datetime import date

import pytest

from stock_grader.grading import Answer, grade, letter_for
from stock_grader.models import DataPoint, MetricHistory

from helpers import data, metric

GROWING = {2021: 100.0, 2022: 110.0, 2023: 120.0, 2024: 130.0}


def answers(result):
    return [q.answer for q in result.questions]


def test_all_yes_is_A():
    r = grade(data(metric(140.0, GROWING), metric(20.0, {2021: 5.0, 2024: 15.0})))
    assert answers(r) == [Answer.YES] * 5
    assert r.letter == "A" and not r.incomplete


@pytest.mark.parametrize("yes,letter", [(5, "A"), (4, "B"), (3, "C"), (2, "D"), (1, "F"), (0, "F")])
def test_grade_scale(yes, letter):
    assert letter_for(yes) == letter


def test_all_no_is_F():
    r = grade(data(metric(90.0, GROWING), metric(-5.0, {2021: 10.0, 2024: 8.0})))
    assert answers(r) == [Answer.NO] * 5
    assert r.letter == "F"


def test_operands_carry_values_and_fiscal_years():
    r = grade(data(metric(140.0, GROWING), metric(20.0, {2021: 5.0, 2024: 15.0})))
    q1, q2, q3 = r.questions[:3]
    assert (q1.left.value, q1.right.value, q1.right.period.fiscal_year) == (140.0, 100.0, 2021)
    assert (q2.right.value, q2.right.period.fiscal_year) == (130.0, 2024)
    assert q1.left.period.period_end == date(2025, 6, 30)
    assert q3.right.kind == "constant" and q3.right.value == 0


def test_equal_values_are_no():
    r = grade(data(metric(100.0, {2021: 100.0, 2024: 100.0}), metric(0.0, {2021: 0.0, 2024: 0.0})))
    assert answers(r) == [Answer.NO] * 5  # y compris FCF TTM = 0 -> pas > 0


def test_ttm_equal_to_latest_annual_adds_note():
    rev = metric(130.0, GROWING, ttm_end=date(2024, 12, 31))
    r = grade(data(rev, metric(20.0, {2021: 5.0, 2024: 15.0})))
    q2 = r.questions[1]
    assert q2.answer is Answer.NO
    assert any("TTM égal au dernier exercice annuel (2024)" in n for n in q2.notes)
    assert any("même date" in n for n in q2.notes)


def test_no_equality_note_when_different():
    r = grade(data(metric(140.0, GROWING), metric(20.0, {2021: 5.0, 2024: 15.0})))
    assert not any("TTM égal" in n for q in r.questions for n in q.notes)


def test_oldest_skips_blank_years():
    rev = metric(140.0, {2020: None, 2021: None, 2022: 120.0, 2024: 130.0})
    q1 = grade(data(rev, metric(1.0, {2024: 0.5}))).questions[0]
    assert q1.right.period.fiscal_year == 2022 and q1.right.value == 120.0


def test_latest_skips_blank_year_with_note():
    rev = metric(125.0, {2022: 100.0, 2023: 120.0, 2024: None})
    q2 = grade(data(rev, metric(1.0, {2024: 0.5}))).questions[1]
    assert q2.right.period.fiscal_year == 2023
    assert q2.answer is Answer.YES
    assert any("2024 sans données" in n for n in q2.notes)


def test_negative_values_compared_numerically():
    fcf = metric(-50e6, {2021: -100e6, 2024: -40e6})
    r = grade(data(metric(140.0, GROWING), fcf))
    q3, q4, q5 = r.questions[2:]
    assert q3.answer is Answer.NO  # -50M n'est pas > 0
    assert q4.answer is Answer.YES  # -50M > -100M : amélioration
    assert q5.answer is Answer.NO  # -50M < -40M


def test_missing_ttm_gives_na_and_incomplete():
    r = grade(data(metric(140.0, GROWING), metric(None, {2021: 5.0, 2024: 15.0})))
    assert answers(r) == [Answer.YES, Answer.YES, Answer.NA, Answer.NA, Answer.NA]
    assert r.incomplete and r.na_count == 3
    # N/A n'est pas compté comme Non : 2 Oui -> D
    assert r.yes_count == 2 and r.letter == "D"
    assert "TTM indisponible" in r.questions[2].notes[0]


def test_no_annual_data_gives_na():
    r = grade(data(metric(140.0, {2023: None, 2024: None}), metric(20.0, {2021: 5.0, 2024: 15.0})))
    assert answers(r)[:2] == [Answer.NA, Answer.NA]
    assert "aucun exercice annuel" in r.questions[0].notes[0]
    assert r.incomplete and r.letter == "C"


def test_nothing_available_is_not_gradable():
    r = grade(data(MetricHistory(), MetricHistory()))
    assert all(a is Answer.NA for a in answers(r))
    assert r.letter is None


def test_single_annual_year_note():
    r = grade(data(metric(140.0, {2024: 130.0}), metric(20.0, {2024: 15.0})))
    assert r.questions[0].right.period.fiscal_year == r.questions[1].right.period.fiscal_year == 2024
    assert any("Un seul exercice" in n for n in r.questions[0].notes)


def test_source_notes_are_propagated():
    fcf = MetricHistory(
        ttm=DataPoint(date(2025, 6, 30), 20.0, "TTM calculé : somme des 4 derniers trimestres"),
        annual=(DataPoint(date(2024, 12, 31), 15.0),),
    )
    r = grade(data(metric(140.0, GROWING), fcf))
    assert "TTM calculé : somme des 4 derniers trimestres" in r.questions[2].notes


def test_same_period_but_different_values_adds_restatement_note():
    rev = metric(131.0, GROWING, ttm_end=date(2024, 12, 31))
    q2 = grade(data(rev, metric(20.0, {2024: 15.0}))).questions[1]
    assert q2.answer is Answer.YES  # la réponse reste numérique
    assert any("même période que l'exercice 2024" in n and "retraitement" in n for n in q2.notes)


def test_ttm_older_than_latest_annual_adds_note():
    rev = metric(125.0, GROWING, ttm_end=date(2024, 6, 30))
    q2 = grade(data(rev, metric(20.0, {2024: 15.0}))).questions[1]
    assert q2.answer is Answer.NO
    assert any("plus ancien que l'exercice 2024" in n for n in q2.notes)


def test_no_period_note_for_normal_ttm():
    q2 = grade(data(metric(140.0, GROWING), metric(20.0, {2024: 15.0}))).questions[1]
    assert q2.notes == ()
