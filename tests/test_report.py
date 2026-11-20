from datetime import date

from stock_grader.grading import grade
from stock_grader.report import compared_periods, describe_earnings, format_date_fr, format_text

from helpers import data, metric

TODAY = date(2026, 11, 20)


def test_french_date():
    assert format_date_fr(date(2027, 2, 25)) == "jeu. 25 févr. 2027"


def test_single_upcoming_date():
    assert describe_earnings((date(2027, 2, 25),), TODAY) == ("jeu. 25 févr. 2027", 97)


def test_estimated_range():
    text, days = describe_earnings((date(2027, 2, 25), date(2027, 3, 1)), TODAY)
    assert text == "entre le jeu. 25 févr. 2027 et le lun. 1 mars 2027 (date estimée)"
    assert days == 97


def test_past_or_missing_date_is_hidden():
    assert describe_earnings((date(2026, 10, 30),), TODAY) is None
    assert describe_earnings((), TODAY) is None


def test_compared_periods_per_question():
    d = data(metric(140.0, {2021: None, 2022: 100.0, 2024: 130.0}), metric(None, {2023: 5.0}))
    q = grade(d).questions
    assert compared_periods(q[0], d) == "TTM au 30/06/2025 vs exercice 2022 · 2021 sans données"
    assert compared_periods(q[1], d) == "TTM au 30/06/2025 vs exercice 2024"
    assert compared_periods(q[2], d) == "FCF TTM indisponible"
    assert compared_periods(q[3], d) == "TTM indisponible vs exercice 2023"


def test_text_report_includes_upcoming_earnings():
    from dataclasses import replace
    from datetime import timedelta

    d = replace(
        data(metric(140.0, {2024: 130.0}), metric(1.0, {2024: 0.5})),
        next_earnings=(date.today() + timedelta(days=10),),
    )
    assert "(dans 10 j)" in format_text(grade(d))
