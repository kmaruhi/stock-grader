"""Tests de l'interface Streamlit avec une source factice (aucun accès réseau)."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from stock_grader.sources import DataSourceError
from stock_grader.sources.yahoo import YFinanceDataSource

from helpers import data, metric

APP = str(Path(__file__).parent.parent / "app.py")

SAMPLES = {
    "AAPL": data(
        metric(410e9, {2021: 365.8e9, 2024: 391.0e9}),
        metric(-50e6, {2021: -100e6, 2024: -40e6}),
        ticker="AAPL",
    ),
    "EQ": data(
        metric(130.0, {2021: 100.0, 2024: 130.0}, ttm_end=date(2024, 12, 31)),
        metric(None, {2024: 15.0}),
        ticker="EQ",
    ),
}


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    def fetch(self, ticker):
        if ticker not in SAMPLES:
            raise DataSourceError(f"Impossible de récupérer les données de {ticker}")
        return SAMPLES[ticker]

    monkeypatch.setattr(YFinanceDataSource, "fetch", fetch)
    import streamlit as st

    st.cache_data.clear()


def run(ticker):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].input(ticker)
    at.button[0].click().run()
    assert not at.exception
    return at


def all_markdown(at):
    return "\n".join(m.value for m in at.markdown)


def test_initial_page_in_french():
    at = AppTest.from_file(APP).run()
    assert not at.exception
    assert at.title[0].value == "📈 Notation d'actions"
    assert at.text_input[0].label == "Ticker"


def test_grade_and_questions_displayed():
    at = run("aapl")  # mis en majuscules
    md = all_markdown(at)
    assert at.subheader[0].value == "AAPL"
    assert "#fbc02d" in md and ">C</div>" in md  # C en jaune
    assert "✅ Oui · Q1." in md and "❌ Non · Q3." in md
    assert "365,80 Md USD (exercice 2021, clos le 31/12/2021)" in md
    assert "\\-50,00 M USD (TTM, 12 mois au 30/06/2025)" in md
    assert not at.warning


def test_na_equality_notes_and_incomplete_warning():
    at = run("EQ")
    md = all_markdown(at)
    captions = "\n".join(c.value for c in at.caption)
    assert "N/A · Q3." in md
    assert "INCOMPLÈTE" in md
    assert "TTM égal au dernier exercice annuel (2024)" in captions
    assert "Un seul exercice annuel" in captions
    assert "ne sont pas comptées" in at.warning[0].value


def test_error_is_shown():
    at = run("NOPE")
    assert "Erreur" in at.error[0].value
