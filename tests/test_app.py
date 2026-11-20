"""Tests de l'interface Streamlit avec une source factice (aucun accès réseau)."""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from stock_grader.models import CompanyMatch
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
SEARCHES = []

# Résultats de recherche factices (la vraie recherche Yahoo n'est jamais appelée).
SEARCH_RESULTS = {
    "apple": [
        CompanyMatch("AAPL", "Apple Inc.", "NASDAQ", "EQUITY"),
        CompanyMatch("AAPU", "Direxion Daily AAPL Bull 2X Shares", "NASDAQ", "ETF"),
    ],
    "lvmh": [
        CompanyMatch("MC.PA", "LVMH Moët Hennessy - Louis Vuitton", "Paris", "EQUITY"),
        CompanyMatch("LVMUY", "LVMH Moët Hennessy - Louis Vuitton", "OTC Markets", "EQUITY"),
        CompanyMatch("LVMH.X", "LVMH Futures", "CME", "FUTURE"),
    ],
    "aapl": [
        CompanyMatch("AAPL", "Apple Inc.", "NASDAQ", "EQUITY"),
        CompanyMatch("AAPL.TO", "Apple CDR", "Toronto", "EQUITY"),
    ],
}


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    CALLS.clear()

    def fetch(self, ticker):
        CALLS.append(ticker)
        if ticker not in SAMPLES:
            raise DataSourceError(f"Impossible de récupérer les données de {ticker}")
        return SAMPLES[ticker]

    def search(self, query):
        SEARCHES.append(query)
        if query == "panne":
            raise DataSourceError("Recherche impossible")
        return SEARCH_RESULTS.get(query.lower(), [])

    SEARCHES.clear()
    monkeypatch.setattr(YFinanceDataSource, "fetch", fetch)
    monkeypatch.setattr(YFinanceDataSource, "search", search)
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
    md = all_markdown(at)
    assert "<div class='sg-h1'>ORA SCORE</div>" in md
    assert "LVLUP with Lani" in md and "data:image/png;base64," in md  # logo de la marque
    assert at.text_input[0].label == "Société ou symbole"
    assert "ne constitue pas un conseil en investissement" in md
    assert at.expander[0].label == "Mode d'emploi"
    assert "MC.PA" in "\n".join(m.value for m in at.expander[0].markdown)


def test_grade_and_questions_displayed():
    at = run("aapl")  # mis en majuscules
    md = all_markdown(at)
    assert at.subheader[0].value == "Apple Inc. `AAPL`"  # nom de la société à côté du ticker
    # Note dans un anneau fin, couleur ocre pour C (thème clair), 3 critères sur 5.
    assert "--sg-grade:#a8823a" in md and "aria-label='Note C'>C</div>" in md
    assert "3 critères validés sur 5" in md
    # Titres courts, périodes comparées sous le titre, montants à droite.
    assert "Chiffre d&#x27;affaires en hausse (global)" in md
    assert "TTM au 30/06/2025 vs exercice 2021" in md
    assert "410,00 Md &#36;</span> <span class='vs'>vs</span> <span class='nw'>365,80 Md &#36;" in md
    assert "<span class='sg-mark yes'>✓</span><small>Oui</small>" in md
    assert "<span class='sg-mark no'>✕</span><small>Non</small>" in md
    # Q3 : un seul montant (comparaison à zéro), en négatif.
    assert "FCF TTM au 30/06/2025" in md and "-50,00 M &#36;" in md
    assert not at.warning


def test_next_earnings_shown_at_bottom():
    md = all_markdown(run("AAPL"))
    assert "Prochains résultats" in md
    assert "97 j</div>" in md


def test_missing_name_and_earnings_are_explained():
    at = run("EQ")
    assert at.subheader[0].value == "`EQ`"
    assert "Nom de la société non communiqué" in captions(at)
    assert "Date des prochains résultats non communiquée" in all_markdown(at)


def test_fallback_years_are_flagged_in_subtitle():
    md = all_markdown(run("GAP"))
    assert "TTM au 30/06/2025 vs exercice 2021 · <span class='sg-warn'>2020 sans données</span>" in md
    assert "TTM au 30/06/2025 vs exercice 2024 · <span class='sg-warn'>2025 sans données</span>" in md
    # FCF : pas d'année manquante, pas d'avertissement ; exercice différent du CA.
    assert "TTM au 30/06/2025 vs exercice 2022</div>" in md


def test_na_equality_notes_and_incomplete_warning():
    at = run("EQ")
    md = all_markdown(at)
    assert "<span class='sg-mark na'>–</span><small>N/A</small>" in md
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
    assert "Aucune société trouvée" in at.warning[0].value
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


def test_report_link_under_result_with_ticker_in_subject():
    md = all_markdown(run("AAPL"))
    assert "[Signaler un problème](mailto:wealthwithlani@gmail.com?subject=" in md
    assert "AAPL" in md.split("subject=")[1]


def test_report_link_hidden_when_not_configured(tmp_path):
    source = Path(APP).read_text(encoding="utf-8")
    source = source.replace('LIEN_SIGNALEMENT = "mailto:wealthwithlani@gmail.com"', 'LIEN_SIGNALEMENT = ""')
    app = tmp_path / "app.py"
    app.write_text(source, encoding="utf-8")
    at = AppTest.from_file(str(app), default_timeout=30)
    at.query_params["ticker"] = "AAPL"
    at.run()
    assert not at.exception
    assert "Signaler un problème" not in all_markdown(at)


def test_search_by_name_with_single_stock_goes_straight_to_grade():
    at = run("Apple")  # une seule action (l'autre résultat est un ETF)
    assert at.subheader[0].value == "Apple Inc. `AAPL`"
    assert at.text_input[0].value == "AAPL"
    assert at.query_params["ticker"] in ("AAPL", ["AAPL"])


def test_exact_symbol_goes_straight_to_grade():
    at = run("aapl")
    assert at.subheader[0].value == "Apple Inc. `AAPL`"
    assert CALLS == ["AAPL"]


def test_ambiguous_name_offers_choices_then_grades_the_chosen_one():
    SAMPLES["MC.PA"] = replace(SAMPLES["AAPL"], ticker="MC.PA", company_name="LVMH")
    try:
        at = run("lvmh")
        assert "Plusieurs sociétés correspondent à « lvmh »" in all_markdown(at)
        labels = [b.label for b in at.button if b.key and b.key.startswith("choix_")]
        assert labels == [
            r"LVMH Moët Hennessy - Louis Vuitton — MC.PA \(Paris\)",  # échappé pour Markdown
            r"LVMH Moët Hennessy - Louis Vuitton — LVMUY \(OTC Markets\)",
        ]  # actions seulement, pas les contrats à terme
        assert not at.subheader and CALLS == []
        next(b for b in at.button if b.key == "choix_MC.PA").click().run()
        assert not at.exception
        assert at.subheader[0].value == "LVMH `MC.PA`"
        assert at.text_input[0].value == "MC.PA"
        assert not any(b.key and b.key.startswith("choix_") for b in at.button)
    finally:
        del SAMPLES["MC.PA"]


def test_search_unavailable_falls_back_to_symbol():
    at = run("panne")
    assert SEARCHES == ["panne"]
    assert CALLS == ["PANNE"]  # essayé comme symbole
    assert "Erreur" in at.error[0].value


def test_result_comes_before_intro_but_home_page_starts_with_it():
    home = AppTest.from_file(APP).run()
    home_md = [m.value for m in home.markdown]
    disclaimer = next(i for i, m in enumerate(home_md) if "conseil en investissement" in m)
    assert disclaimer < len(home_md) - 1  # avertissement pédagogique en haut de l'accueil
    at = run("AAPL")
    md = [m.value for m in at.markdown]
    # Sur la page de résultat : en-tête compact, puis la note, puis la présentation.
    assert "sg-brand compact" in md[1] and "sg-lead" not in md[1]
    grade_index = next(i for i, m in enumerate(md) if "aria-label='Note C'" in m)
    intro_index = next(i for i, m in enumerate(md) if "Note de A à F" in m)
    disclaimer_index = next(i for i, m in enumerate(md) if "conseil en investissement" in m)
    assert grade_index < intro_index < disclaimer_index


def app_functions():
    """Fonctions de app.py, sans lancer la page."""
    source = Path(APP).read_text(encoding="utf-8").replace("\nmain()\n", "\n")
    namespace = {"__name__": "app_functions", "__file__": APP}
    exec(compile(source, APP, "exec"), namespace)
    return namespace


def test_dark_theme_has_its_own_logo_and_colors():
    app = app_functions()
    assert app["logo_data_uri"]("light") != app["logo_data_uri"]("dark")
    assert "--sg-accent:#8fc4a1" in app["theme_css"]("dark")
    assert "--sg-accent:#2f5d46" in app["theme_css"]("light")


def test_criteria_wording():
    criteria_text = app_functions()["criteria_text"]
    assert criteria_text(0, 5) == "Aucun critère validé sur 5"
    assert criteria_text(1, 5) == "1 critère validé sur 5"
    assert criteria_text(4, 4) == "4 critères validés sur 4"
