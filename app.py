"""Interface web Streamlit : streamlit run app.py"""

from __future__ import annotations

import streamlit as st

from stock_grader.grading import Answer, GradeResult, QuestionResult, grade
from stock_grader.models import FinancialData
from stock_grader.report import describe_operand, grade_title
from stock_grader.sources import DataSourceError
from stock_grader.sources.yahoo import YFinanceDataSource

CACHE_TTL_SECONDS = 24 * 60 * 60

# Fond et couleur du texte du badge, du vert (A) au rouge (F).
GRADE_COLORS = {
    "A": ("#1e8e3e", "#ffffff"),
    "B": ("#7cb342", "#ffffff"),
    "C": ("#fbc02d", "#1f1f1f"),
    "D": ("#ef6c00", "#ffffff"),
    "F": ("#d32f2f", "#ffffff"),
    None: ("#9e9e9e", "#ffffff"),
}

ANSWER_BADGES = {Answer.YES: "✅ Oui", Answer.NO: "❌ Non", Answer.NA: "N/A"}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_data(ticker: str) -> FinancialData:
    # Les exceptions (DataSourceError) ne sont pas mises en cache par Streamlit.
    return YFinanceDataSource().fetch(ticker)


def render_grade(result: GradeResult) -> None:
    background, color = GRADE_COLORS.get(result.letter, GRADE_COLORS[None])
    letter = result.letter or "?"
    summary = f"{result.yes_count} Oui sur {result.answered_count} question(s) évaluée(s)"
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:1.5rem;margin:1rem 0 1.5rem;">
          <div style="background:{background};color:{color};font-size:5.5rem;font-weight:800;
                      line-height:1;width:9rem;height:9rem;border-radius:1.25rem;
                      display:flex;align-items:center;justify-content:center;">{letter}</div>
          <div>
            <div style="font-size:1.6rem;font-weight:700;">{grade_title(result)}</div>
            <div style="opacity:0.75;">{summary}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if result.incomplete:
        st.warning(
            f"Note incomplète : {result.na_count} question(s) N/A. Elles ne sont pas comptées "
            "comme Non ; la note porte uniquement sur les questions évaluées."
        )


def _plain(text: str) -> str:
    """Évite qu'un montant négatif en début de ligne soit rendu comme une liste Markdown."""
    return "\\" + text if text.startswith("-") else text


def render_question(q: QuestionResult, currency: str | None) -> None:
    with st.container(border=True):
        st.markdown(f"**{ANSWER_BADGES[q.answer]} · Q{q.number}. {q.label}**")
        left, sign, right = st.columns([5, 1, 5], vertical_alignment="center")
        left.markdown(_plain(describe_operand(q.left, currency)))
        sign.markdown("<div style='text-align:center;font-size:1.4rem;'>&gt;</div>", unsafe_allow_html=True)
        right.markdown(_plain(describe_operand(q.right, currency)))
        for note in q.notes:
            st.caption(f"ℹ️ {note}")


def main() -> None:
    st.set_page_config(page_title="Notation d'actions", page_icon="📈", layout="centered")
    st.title("📈 Notation d'actions")
    st.write(
        "Note de A à F selon l'évolution du chiffre d'affaires et du Free Cash Flow "
        "(TTM comparé aux exercices annuels, données Yahoo Finance)."
    )

    with st.form("recherche"):
        ticker = st.text_input("Ticker", placeholder="ex. AAPL, MSFT, MC.PA").strip().upper()
        submitted = st.form_submit_button("Noter", type="primary")

    if not (submitted and ticker):
        st.caption("Saisissez un symbole Yahoo Finance (suffixe .PA pour Paris, .DE pour Francfort, etc.).")
        return

    with st.spinner(f"Récupération des données de {ticker}…"):
        try:
            data = fetch_data(ticker)
        except DataSourceError as exc:
            st.error(f"Erreur : {exc}")
            return

    result = grade(data)
    st.subheader(data.ticker + (f" — {data.company_name}" if data.company_name else ""))
    render_grade(result)
    for q in result.questions:
        render_question(q, data.currency)
    st.caption("Données mises en cache 24 h. Source : Yahoo Finance via yfinance.")


main()
