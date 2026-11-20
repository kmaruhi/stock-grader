"""Tests de l'interface Streamlit avec une source factice (aucun accès réseau)."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from stock_grader.sources import DataSourceError
from stock_grader.sources.yahoo import YFinanceDataSource

from helpers import data, metric

APP = str(Path(__file__).parent.parent / "app.py")

SOON = date.today() + timedelta(days=97)

SAMPLES = {
    "AAPL": replace(
        data(
            metric(410e9, {2021: 365.8e9, 2024: 391.0e9}),
            metric(-50e6, {2021: -100e6, 2024: -40e6}),
            ticker="AAPL",
        ),
        company_name="Apple Inc.",
        next_earnings=(SOON,),
    ),
    # 2020 (plus ancien) et 2025 (plus récent) vides pour le CA : années de repli.
    "GAP": data(
        metric(140.0, {2020: None, 2021: 100.0, 2024: 130.0, 2025: None}),
        metric(20.0, {2022: 5.0, 2024: 15.0}),
        ticker="GAP",
    ),
    "EQ": data(
        metric(130.0, {2021: 100.0, 2024: 130.0}, ttm_end=date(2024, 12, 31)),
        metric(None, {2024: 15.0}),
        ticker="EQ",
    ),
}


CALLS = []


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    CALLS.clear()

    def fetch(self, ticker):
        CALLS.append(ticker)
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
    assert "ne constitue pas un conseil en investissement" in at.info[0].value
    assert at.expander[0].label == "Mode d'emploi"
    assert "MC.PA" in "\n".join(m.value for m in at.expander[0].markdown)


def test_grade_and_questions_displayed():
    at = run("aapl")  # mis en majuscules
    md = all_markdown(at)
    assert at.subheader[0].value == "Apple Inc. `AAPL`"  # nom de la société à côté du ticker
    assert "#fbc02d" in md and ">C</div>" in md  # C en jaune
    # Titres courts, périodes comparées sous le titre, montants à droite.
    assert "Chiffre d&#x27;affaires en hausse (global)" in md
    assert "TTM au 30/06/2025 vs exercice 2021" in md
    assert "410,00 Md &#36;</span> vs <span class='nw'>365,80 Md &#36;" in md
    assert "✅<small>Oui</small>" in md and "❌<small>Non</small>" in md
    # Q3 : un seul montant (comparaison à zéro), en négatif.
    assert "FCF TTM au 30/06/2025" in md and "-50,00 M &#36;" in md
    assert not at.warning


def test_next_earnings_shown_at_bottom():
    md = all_markdown(run("AAPL"))
    assert "📅 Prochains résultats" in md
    assert "⏱ 97 j" in md


def test_missing_name_and_earnings_are_explained():
    at = run("EQ")
    assert at.subheader[0].value == "`EQ`"
    assert "Nom de la société non communiqué" in captions(at)
    assert "Date des prochains résultats non communiquée" in all_markdown(at)


def test_fallback_years_are_flagged_in_subtitle():
    md = all_markdown(run("GAP"))
    assert "TTM au 30/06/2025 vs exercice 2021 · <span class='sg-warn'>⚠️ 2020 sans données</span>" in md
    assert "TTM au 30/06/2025 vs exercice 2024 · <span class='sg-warn'>⚠️ 2025 sans données</span>" in md
    # FCF : pas d'année manquante, pas d'avertissement ; exercice différent du CA.
    assert "TTM au 30/06/2025 vs exercice 2022</div>" in md


def test_na_equality_notes_and_incomplete_warning():
    at = run("EQ")
    md = all_markdown(at)
    assert "N/A</div>" in md
    assert "INCOMPLÈTE" in md
    assert "TTM égal au dernier exercice annuel (2024)" in md
    assert "Un seul exercice annuel" in md
    assert "ne sont pas comptées" in at.warning[0].value


def test_error_is_shown():
    at = run("NOPE")
    assert "Erreur" in at.error[0].value


def captions(at):
    return "\n".join(c.value for c in at.caption)


def test_complete_result_is_cached_and_shown_with_timestamp():
    at = run("AAPL")
    assert "récupérées le" in captions(at) and "cache 24 h" in captions(at)
    run("AAPL")
    assert CALLS == ["AAPL"]


def test_incomplete_result_is_not_cached():
    at = run("EQ")
    assert "non conservé en cache" in captions(at)
    run("EQ")
    assert CALLS == ["EQ", "EQ"]


def test_ticker_in_url_survives_reruns_and_refresh_refetches():
    at = run("AAPL")
    assert at.query_params["ticker"] in ("AAPL", ["AAPL"])  # format selon la version de Streamlit
    refresh = next(b for b in at.button if b.label == "Actualiser")
    refresh.click().run()
    assert not at.exception
    assert at.subheader[0].value == "Apple Inc. `AAPL`"  # toujours affiché après réexécution
    assert CALLS == ["AAPL", "AAPL"]


def test_shared_link_loads_ticker():
    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["ticker"] = "AAPL"
    at.run()
    assert at.subheader[0].value == "Apple Inc. `AAPL`"
    assert at.text_input[0].value == "AAPL"


def test_invalid_ticker_rejected_without_fetch():
    at = run("AA PL; <b>")
    assert "n'est pas un ticker valide" in at.error[0].value
    assert CALLS == []


def test_second_search_shows_new_ticker_immediately():
    # Régression : la 2e recherche réaffichait le ticker précédent.
    at = run("AAPL")
    at.text_input[0].input("EQ")
    at.button[0].click().run()
    assert at.subheader[0].value == "`EQ`"
    assert at.text_input[0].value == "EQ"
    at.text_input[0].input("aapl")
    at.button[0].click().run()
    assert at.subheader[0].value == "Apple Inc. `AAPL`"


def test_report_link_hidden_until_configured():
    md = all_markdown(run("AAPL"))
    assert "Signaler un problème" not in md


def test_report_link_shown_with_ticker_in_email_subject(tmp_path):
    source = Path(APP).read_text(encoding="utf-8").replace(
        'LIEN_SIGNALEMENT = ""', 'LIEN_SIGNALEMENT = "mailto:prof@example.com"'
    )
    app = tmp_path / "app.py"
    app.write_text(source, encoding="utf-8")
    at = AppTest.from_file(str(app), default_timeout=30)
    at.query_params["ticker"] = "AAPL"
    at.run()
    assert not at.exception
    md = all_markdown(at)
    assert "[Signaler un problème](mailto:prof@example.com?subject=" in md
    assert "AAPL" in md.split("subject=")[1]
