"""Interface web Streamlit : streamlit run app.py"""

from __future__ import annotations

import html
import re
from urllib.parse import quote
from datetime import date, datetime, timezone

import streamlit as st

from stock_grader.grading import Answer, GradeResult, QuestionResult, grade
from stock_grader.models import FinancialData
from stock_grader.report import (
    SHORT_TITLES,
    compared_periods,
    describe_earnings,
    format_amount,
    grade_title,
)
from stock_grader.sources import DataSourceError
from stock_grader.sources.yahoo import YFinanceDataSource

CACHE_TTL_SECONDS = 24 * 60 * 60

# Lien « Signaler un problème » : adresse d'un formulaire (ex. Google Forms) ou
# « mailto:adresse@exemple.com ». Vide = lien masqué. Le dépôt étant public, ce lien
# est visible de tous.
LIEN_SIGNALEMENT = ""
TICKER_PATTERN = re.compile(r"[A-Z0-9.\-^=]{1,20}")

# Fond et couleur du texte du badge, du vert (A) au rouge (F).
GRADE_COLORS = {
    "A": ("#1e8e3e", "#ffffff"),
    "B": ("#7cb342", "#ffffff"),
    "C": ("#fbc02d", "#1f1f1f"),
    "D": ("#ef6c00", "#ffffff"),
    "F": ("#d32f2f", "#ffffff"),
    None: ("#9e9e9e", "#ffffff"),
}

DISCLAIMER = (
    "Outil pédagogique : cette note ne constitue pas un conseil en investissement. "
    "Les données proviennent de Yahoo Finance et peuvent contenir des erreurs ou des retards."
)

HOW_TO = """
**1. Saisir un ticker** (le symbole de l'action sur Yahoo Finance), puis cliquer sur « Noter ».
- Actions américaines : le symbole seul, ex. `AAPL` (Apple), `MSFT` (Microsoft).
- Autres places : ajouter le suffixe de la bourse, ex. `MC.PA` (LVMH, Paris),
  `SAP.DE` (Francfort), `SHOP.TO` (Toronto). En cas de doute, chercher la société
  sur finance.yahoo.com et recopier le symbole affiché.

**2. Lire les 5 questions.**

| # | Titre affiché | Question posée |
|---|---|---|
| 1 | Chiffre d'affaires en hausse (global) | CA TTM > plus ancien CA annuel disponible ? |
| 2 | Chiffre d'affaires en hausse (récent) | CA TTM > CA annuel le plus récent ? |
| 3 | Free Cash Flow positif | FCF TTM > 0 ? |
| 4 | Free Cash Flow en hausse (global) | FCF TTM > plus ancien FCF annuel disponible ? |
| 5 | Free Cash Flow en hausse (récent) | FCF TTM > FCF annuel le plus récent ? |

Sous chaque titre, la ligne grise indique **les périodes comparées** (ex. « TTM au
30/06/2025 vs exercice 2023 »), et les deux montants sont affichés à droite. Si une
année n'a pas de données chez Yahoo, l'exercice disponible le plus proche est utilisé
et l'année manquante est signalée. Chaque question compare deux montants :
- **TTM** (*trailing twelve months*) = les 12 derniers mois publiés ;
- **exercice** = une année comptable complète (l'année de clôture est indiquée).
- Le **Free Cash Flow** (FCF) est la trésorerie générée par l'activité, après investissements.

| Réponse | Signification |
|---|---|
| ✅ Oui | le TTM est strictement supérieur |
| ❌ Non | le TTM est inférieur **ou égal** |
| N/A | comparaison impossible faute de données (ne compte pas comme Non) |

**3. Lire la note** selon le nombre de « Oui » : 5 = **A**, 4 = **B**, 3 = **C**,
2 = **D** (sous-performance), 0 ou 1 = **F**. Une note **INCOMPLÈTE** signifie
qu'au moins une question est N/A.

**4. Lire les notes ℹ️** sous les questions : elles expliquent les cas particuliers
(TTM égal au dernier exercice juste après un rapport annuel, année sans données, etc.).

Astuce : l'adresse de la page contient le ticker (`?ticker=MC.PA`) ; on peut la copier
pour partager directement un résultat.
"""

ANSWER_ICONS = {Answer.YES: "✅", Answer.NO: "❌", Answer.NA: "N/A"}
ANSWER_LABELS = {Answer.YES: "Oui", Answer.NO: "Non", Answer.NA: "N/A"}

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "$ CA", "CHF": "CHF"}

# Styles des lignes de questions et de l'encart « Prochains résultats ».
# Couleurs neutres (transparences) pour rester lisibles en thème clair comme sombre.
CSS = """
<style>
.sg-list {border:1px solid rgba(128,128,128,.3); border-radius:.75rem; overflow:hidden;}
.sg-row {display:flex; align-items:center; gap:.9rem; padding:.85rem 1rem;}
.sg-row + .sg-row, .sg-item + .sg-item {border-top:1px solid rgba(128,128,128,.2);}
.sg-icon {flex:0 0 2.2rem; text-align:center; font-size:1.15rem; font-weight:700;}
.sg-icon small {display:block; font-size:.7rem; font-weight:400; opacity:.7;}
.sg-main {flex:1 1 auto; min-width:0;}
.sg-title {font-weight:600;}
.sg-sub {font-size:.85rem; opacity:.65;}
.sg-sub .sg-warn {opacity:1; color:#ef6c00;}
.sg-values {flex:0 1 45%; text-align:right; font-variant-numeric:tabular-nums;}
.sg-values .nw {white-space:nowrap;}
.sg-notes {padding:0 1rem .85rem 4.1rem; font-size:.8rem; opacity:.7;}
.sg-notes div + div {margin-top:.25rem;}
.sg-card {display:flex; align-items:center; justify-content:space-between; gap:1rem;
          border:1px solid rgba(128,128,128,.3); border-radius:.75rem; padding:.85rem 1rem; margin:1rem 0 .75rem;}
.sg-muted {font-size:.85rem; opacity:.65; margin:1rem 0 .75rem;}
.sg-days {font-size:1.6rem; font-weight:700; white-space:nowrap;}
</style>
"""


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_data(ticker: str) -> tuple[FinancialData, datetime]:
    # Les exceptions (DataSourceError) ne sont pas mises en cache par Streamlit.
    return YFinanceDataSource().fetch(ticker), datetime.now(timezone.utc)


def _escape_md(text: str) -> str:
    """Échappe les caractères Markdown d'un nom de société (ex. « * » ou « _ »)."""
    return re.sub(r"([\\`*_{}\[\]<>()#+!|$~])", r"\\\1", text)


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


def _amount(value: float | None, currency: str | None) -> str:
    if value is None:
        return "—"
    symbol = CURRENCY_SYMBOLS.get(currency or "", currency)
    # « $ » est échappé : Streamlit interprète « $…$ » comme une formule mathématique.
    text = html.escape(format_amount(value, symbol)).replace("$", "&#36;")
    return f"<span class='nw'>{text}</span>"


def question_html(q: QuestionResult, data: FinancialData) -> str:
    if q.right.kind == "constant":
        values = _amount(q.left.value, data.currency)
    else:
        values = f"{_amount(q.left.value, data.currency)} vs {_amount(q.right.value, data.currency)}"
    periods = html.escape(compared_periods(q, data))
    # Mise en évidence quand l'exercice comparé n'est pas celui attendu (année sans données).
    if " · " in periods:
        main, warn = periods.split(" · ", 1)
        periods = f"{main} · <span class='sg-warn'>⚠️ {warn}</span>"
    icon = ANSWER_ICONS[q.answer]
    label = ANSWER_LABELS[q.answer]
    icon_html = icon if q.answer is Answer.NA else f"{icon}<small>{label}</small>"
    row = (
        f"<div class='sg-row' title='Q{q.number}. {html.escape(q.label, quote=True)}'>"
        f"<div class='sg-icon'>{icon_html}</div>"
        f"<div class='sg-main'><div class='sg-title'>{html.escape(SHORT_TITLES[q.number])}</div>"
        f"<div class='sg-sub'>{periods}</div></div>"
        f"<div class='sg-values'>{values}</div></div>"
    )
    notes = "".join(f"<div>ℹ️ {html.escape(n)}</div>" for n in q.notes)
    if notes:
        row += f"<div class='sg-notes'>{notes}</div>"
    return f"<div class='sg-item'>{row}</div>"


def render_questions(result: GradeResult, data: FinancialData) -> None:
    items = "".join(question_html(q, data) for q in result.questions)
    st.markdown(f"<div class='sg-list'>{items}</div>", unsafe_allow_html=True)


def render_earnings(data: FinancialData, today: date) -> None:
    earnings = describe_earnings(data.next_earnings, today)
    if earnings is None:
        st.markdown(
            "<div class='sg-muted'>📅 Date des prochains résultats non communiquée par Yahoo Finance.</div>",
            unsafe_allow_html=True,
        )
        return
    text, days = earnings
    countdown = "aujourd'hui" if days == 0 else f"⏱ {days} j"
    st.markdown(
        "<div class='sg-card'><div><div class='sg-title'>📅 Prochains résultats</div>"
        f"<div class='sg-sub'>{html.escape(text)}</div></div>"
        f"<div class='sg-days' title='Nombre de jours restants'>{countdown}</div></div>",
        unsafe_allow_html=True,
    )


def report_link(ticker: str | None = None) -> str | None:
    """Lien de signalement ; pour un e-mail, l'objet mentionne le ticker consulté."""
    if not LIEN_SIGNALEMENT:
        return None
    if LIEN_SIGNALEMENT.startswith("mailto:") and ticker:
        return f"{LIEN_SIGNALEMENT}?subject={quote(f'Notation d’actions : problème avec {ticker}')}"
    return LIEN_SIGNALEMENT


def _submit_search() -> None:
    """Appelé au clic sur « Noter », avant la réexécution de la page."""
    ticker = st.session_state["ticker_input"].strip().upper()
    st.session_state["ticker_input"] = ticker
    st.query_params["ticker"] = ticker


def main() -> None:
    st.set_page_config(page_title="Notation d'actions", page_icon="📈", layout="centered")
    st.title("📈 Notation d'actions")
    st.write(
        "Note de A à F selon l'évolution du chiffre d'affaires et du Free Cash Flow "
        "(TTM comparé aux exercices annuels, données Yahoo Finance)."
    )
    st.info(DISCLAIMER, icon="🎓")
    with st.expander("Mode d'emploi"):
        st.markdown(HOW_TO)

    # Le ticker courant vit dans l'URL (?ticker=AAPL) : lien partageable, et le
    # résultat reste affiché lors des réexécutions (ex. bouton « Actualiser »).
    # Le champ a une clé fixe : s'il était recréé avec une nouvelle valeur par défaut à
    # chaque recherche, Streamlit le traiterait comme un nouveau champ et perdrait la
    # saisie (il fallait alors chercher deux fois).
    if "ticker_input" not in st.session_state:
        st.session_state["ticker_input"] = st.query_params.get("ticker", "")
    with st.form("recherche"):
        st.text_input("Ticker", key="ticker_input", placeholder="ex. AAPL, MSFT, MC.PA")
        st.form_submit_button("Noter", type="primary", on_click=_submit_search)
    current = st.query_params.get("ticker", "")

    if not current:
        st.caption("Saisissez un symbole Yahoo Finance (suffixe .PA pour Paris, .DE pour Francfort, etc.).")
        return
    if not TICKER_PATTERN.fullmatch(current):
        st.error(f"« {current} » n'est pas un ticker valide (lettres, chiffres et . - ^ = uniquement).")
        return

    with st.spinner(f"Récupération des données de {current}…"):
        try:
            data, fetched_at = fetch_data(current)
        except DataSourceError as exc:
            st.error(f"Erreur : {exc}")
            return

    result = grade(data)
    st.markdown(CSS, unsafe_allow_html=True)
    if data.company_name:
        st.subheader(f"{_escape_md(data.company_name)} `{data.ticker}`")
    else:
        st.subheader(f"`{data.ticker}`")
        st.caption("Nom de la société non communiqué par Yahoo Finance.")
    render_grade(result)
    render_questions(result, data)
    render_earnings(data, date.today())

    if result.incomplete:
        # Un résultat incomplet peut venir d'une erreur passagère de Yahoo (masquée par
        # yfinance) : on ne le garde pas 24 h en cache.
        fetch_data.clear(current)
        cache_info = "Résultat incomplet : non conservé en cache, il sera redemandé à Yahoo à la prochaine recherche."
    else:
        cache_info = "Données conservées en cache 24 h."
    info_col, button_col = st.columns([4, 1], vertical_alignment="center")
    info_col.caption(
        f"Données Yahoo Finance récupérées le {fetched_at:%d/%m/%Y à %H:%M} UTC. {cache_info}"
    )
    link = report_link(current)
    if link:
        st.markdown(f"🚩 Un résultat vous semble faux ? [Signaler un problème]({link})")
    if button_col.button("Actualiser", help="Ignorer le cache et interroger de nouveau Yahoo Finance"):
        fetch_data.clear(current)
        st.rerun()


main()
