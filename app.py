"""Interface web Streamlit : streamlit run app.py"""

from __future__ import annotations

import base64
import html
import re
from functools import cache
from pathlib import Path
from urllib.parse import quote
from datetime import date, datetime, timezone

import streamlit as st

from stock_grader.grading import Answer, GradeResult, QuestionResult, grade
from stock_grader.models import CompanyMatch, FinancialData
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
LIEN_SIGNALEMENT = "mailto:wealthwithlani@gmail.com"
TICKER_PATTERN = re.compile(r"[A-Z0-9.\-^=]{1,20}")
MAX_CHOICES = 6  # sociétés proposées quand une recherche par nom est ambiguë

# Couleur de la note, du vert forêt (A) au rouge brique (F), par thème (clair / sombre).
GRADE_COLORS = {
    "light": {"A": "#2f5d46", "B": "#5f8a63", "C": "#a8823a", "D": "#b0643d", "F": "#9b3f3f", None: "#8a8178"},
    "dark": {"A": "#8fc4a1", "B": "#b5cf9c", "C": "#e0bd73", "D": "#e3976b", "F": "#e08a8a", None: "#9a948c"},
}

ASSETS = Path(__file__).parent / "assets"
BRAND = "LVLUP with Lani"
APP_NAME = "ORA SCORE"

DISCLAIMER = (
    "Outil pédagogique : cette note ne constitue pas un conseil en investissement. "
    "Les données proviennent de Yahoo Finance et peuvent contenir des erreurs ou des retards."
)

# Rappel d'une ligne sous les questions (remplace l'ancien mode d'emploi).
HINT = (
    "<b>TTM</b> = les 12 derniers mois publiés · <b>Exercice</b> = une année comptable complète · "
    "<b>N/A</b> = donnée manquante chez Yahoo, non comptée comme Non."
)

ANSWER_ICONS = {Answer.YES: "✓", Answer.NO: "✕", Answer.NA: "–"}
ANSWER_CLASSES = {Answer.YES: "yes", Answer.NO: "no", Answer.NA: "na"}
ANSWER_LABELS = {Answer.YES: "Oui", Answer.NO: "Non", Answer.NA: "N/A"}

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "$ CA", "CHF": "CHF"}

# Feuille de style. Les couleurs dépendent du thème (clair / sombre) : voir theme_css().
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Marcellus&display=swap');
.block-container, [data-testid="stMainBlockContainer"] {padding-top:3.5rem; max-width:46rem;}
@media (max-width:640px) {
  .block-container, [data-testid="stMainBlockContainer"] {padding-top:3.25rem;}
}
.stApp {background-image: var(--sg-glow); background-attachment: fixed;}
h1, h2, h3 {letter-spacing:.01em;}
h3 code {font-family:'Jost',sans-serif !important; font-size:.5em !important; font-weight:500; letter-spacing:.14em;
         background:transparent !important; border:1px solid var(--sg-line-strong); border-radius:999px;
         padding:.25em .85em !important; color:inherit !important; vertical-align:middle;}
.stMarkdown a {color:var(--sg-accent); text-decoration-thickness:1px; text-underline-offset:3px;}

/* En-tête de marque */
.sg-brand {width:100%; display:flex; flex-direction:column; align-items:center; text-align:center;
           gap:clamp(.5rem, 1.8vw, .85rem); margin:0 0 1.75rem;}
.sg-brand img {width:22%; max-width:7rem; height:auto;}
.sg-wordmark {font-family:'Marcellus',serif; text-transform:uppercase; opacity:.85;
              font-size:clamp(.72rem, 2.4vw, .9rem); letter-spacing:.32em; padding-left:.32em;}
.sg-h1 {font-family:'Cormorant Garamond',serif; font-weight:500; line-height:1.05;
        font-size:clamp(2.2rem, 9vw, 3.4rem); letter-spacing:.18em; padding-left:.18em;}
.sg-brand .sg-lead, .sg-lead {width:100%; max-width:90%; margin:0; opacity:.7; font-weight:300; line-height:1.55;
          font-size:clamp(1rem, 3.4vw, 1.15rem);}
@media (min-width:768px) {.sg-brand .sg-lead, .sg-lead {max-width:65%;}}
/* Au-dessus d'un résultat : même centrage, logo et titre réduits d'environ 40 %. */
.sg-brand.compact {gap:clamp(.35rem, 1.2vw, .55rem); margin:0 0 1rem;}
.sg-brand.compact img {width:13%; max-width:4.2rem;}
.sg-brand.compact .sg-h1 {font-size:clamp(1.3rem, 5.4vw, 2.05rem);}
.sg-disclaimer {border-left:2px solid var(--sg-accent); padding:.35rem 0 .35rem .9rem;
                font-size:.85rem; font-weight:300; opacity:.8; margin:1.25rem 0;}

/* Note : anneau fin et sobre */
.sg-grade {display:flex; align-items:center; gap:1.4rem; margin:.75rem 0 1.5rem;}
.sg-ring {flex:0 0 auto; width:5.5rem; height:5.5rem; border-radius:50%;
          border:1.5px solid var(--sg-grade); color:var(--sg-grade);
          display:flex; align-items:center; justify-content:center;
          font-family:'Cormorant Garamond',serif; font-weight:500; font-size:3.4rem; line-height:1;}
.sg-eyebrow {font-size:.72rem; letter-spacing:.22em; text-transform:uppercase; opacity:.6;}
.sg-grade-main {font-family:'Cormorant Garamond',serif; font-size:1.55rem; font-weight:500; line-height:1.25;}
.sg-grade-extra {font-size:.85rem; opacity:.75;}
.sg-dots {display:flex; gap:.4rem; margin-top:.5rem;}
.sg-dots span {width:.55rem; height:.55rem; border-radius:50%; border:1.5px solid var(--sg-grade);}
.sg-dots span.yes {background:var(--sg-grade);}
.sg-dots span.na {border-style:dashed; opacity:.6;}

/* Questions */
.sg-list {border:1px solid var(--sg-line); border-radius:1rem; overflow:hidden; background:var(--sg-card);}
.sg-row {display:flex; align-items:center; gap:.9rem; padding:.95rem 1.1rem;}
.sg-row + .sg-row, .sg-item + .sg-item {border-top:1px solid var(--sg-line);}
.sg-icon {flex:0 0 2.2rem; text-align:center;}
.sg-mark {display:inline-flex; width:1.6rem; height:1.6rem; border-radius:50%; align-items:center;
          justify-content:center; font-size:.85rem; font-weight:600;}
.sg-mark.yes {background:var(--sg-yes-bg); color:var(--sg-yes);}
.sg-mark.no {background:var(--sg-no-bg); color:var(--sg-no);}
.sg-mark.na {border:1px dashed var(--sg-line-strong); opacity:.7;}
.sg-icon small {display:block; font-size:.68rem; letter-spacing:.06em; opacity:.6; margin-top:.15rem;}
.sg-main {flex:1 1 auto; min-width:0;}
.sg-title {font-weight:500;}
.sg-sub {font-size:.82rem; font-weight:300; opacity:.7;}
.sg-sub .sg-warn {opacity:1; color:var(--sg-warn);}
.sg-values {flex:0 1 45%; text-align:right; font-variant-numeric:tabular-nums; font-size:.95rem;}
.sg-values .nw {white-space:nowrap;}
.sg-values .vs {opacity:.5; font-size:.8rem; padding:0 .15rem;}
.sg-notes {padding:0 1.1rem .9rem 4.25rem; font-size:.78rem; font-weight:300; opacity:.75;}
.sg-notes div + div {margin-top:.25rem;}
.sg-hint {font-size:.78rem; font-weight:300; opacity:.65; margin:.6rem .25rem 0;}
.sg-hint b {font-weight:500;}
.sg-card {display:flex; align-items:center; justify-content:space-between; gap:1rem; background:var(--sg-card);
          border:1px solid var(--sg-line); border-radius:1rem; padding:.95rem 1.1rem; margin:1rem 0 .75rem;}
.sg-muted {font-size:.85rem; opacity:.65; margin:1rem 0 .75rem;}
.sg-days {font-family:'Cormorant Garamond',serif; font-size:1.8rem; font-weight:500; white-space:nowrap;}

/* Boutons en forme de pilule */
.stButton button, .stFormSubmitButton button {border-radius:999px; padding-left:1.4rem; padding-right:1.4rem;}
</style>
"""

THEME_VARIABLES = {
    "light": {
        "accent": "#2f5d46",
        "line": "rgba(58,46,42,.12)",
        "line-strong": "rgba(58,46,42,.3)",
        "card": "rgba(255,255,255,.65)",
        "yes": "#2f5d46",
        "yes-bg": "rgba(47,93,70,.1)",
        "no": "#9b3f3f",
        "no-bg": "rgba(155,63,63,.08)",
        "warn": "#a8823a",
        "glow": "radial-gradient(ellipse 80% 45% at 50% -5%, rgba(47,93,70,.10), transparent 70%)",
    },
    "dark": {
        "accent": "#8fc4a1",
        "line": "rgba(236,230,220,.09)",
        "line-strong": "rgba(236,230,220,.3)",
        "card": "rgba(255,255,255,.025)",
        "yes": "#8fc4a1",
        "yes-bg": "rgba(143,196,161,.12)",
        "no": "#e08a8a",
        "no-bg": "rgba(224,138,138,.1)",
        "warn": "#e0bd73",
        "glow": "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(77,138,104,.22), transparent 70%)",
    },
}


def theme_type() -> str:
    """« light » ou « dark » selon le thème affiché chez l'élève (clair par défaut)."""
    try:
        kind = st.context.theme.type
    except Exception:
        kind = None
    return "dark" if kind == "dark" else "light"


def theme_css(theme: str) -> str:
    variables = "".join(f"--sg-{name}:{value};" for name, value in THEME_VARIABLES[theme].items())
    return f"<style>:root {{{variables}}}</style>"


@cache
def logo_data_uri(theme: str) -> str | None:
    """Logo intégré à la page (version claire ou sombre) ; None si le fichier manque."""
    path = ASSETS / ("logo_sombre.png" if theme == "dark" else "logo_clair.png")
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_data(ticker: str) -> tuple[FinancialData, datetime]:
    # Les exceptions (DataSourceError) ne sont pas mises en cache par Streamlit.
    return YFinanceDataSource().fetch(ticker), datetime.now(timezone.utc)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def search_companies(query: str) -> list[CompanyMatch]:
    return YFinanceDataSource().search(query)


def resolve_search(query: str, matches: list[CompanyMatch]) -> tuple[str | None, list[CompanyMatch]]:
    """Symbole à noter directement, sinon la liste des sociétés à proposer.

    - symbole exact (ex. « aapl ») ou une seule action trouvée : noté directement ;
    - plusieurs actions (ex. « netflix » : Nasdaq, Francfort, Mexico…) : liste de choix ;
    - rien trouvé (ou recherche indisponible) : le texte est essayé comme symbole.
    """
    symbol = query.strip().upper()
    if any(m.symbol == symbol for m in matches):
        return symbol, []
    stocks = [m for m in matches if m.kind == "EQUITY"][:MAX_CHOICES]
    if len(stocks) == 1:
        return stocks[0].symbol, []
    if stocks:
        return None, stocks
    if TICKER_PATTERN.fullmatch(symbol):
        return symbol, []
    return None, []


def choice_label(match: CompanyMatch) -> str:
    exchange = f" ({match.exchange})" if match.exchange else ""
    return _escape_md(f"{match.name} — {match.symbol}{exchange}")


def _escape_md(text: str) -> str:
    """Échappe les caractères Markdown d'un nom de société (ex. « * » ou « _ »)."""
    return re.sub(r"([\\`*_{}\[\]<>()#+!|$~])", r"\\\1", text)


def criteria_text(yes: int, answered: int) -> str:
    if yes == 0:
        return f"Aucun critère validé sur {answered}"
    if yes == 1:
        return f"1 critère validé sur {answered}"
    return f"{yes} critères validés sur {answered}"


def render_grade(result: GradeResult, theme: str = "light") -> None:
    color = GRADE_COLORS[theme].get(result.letter, GRADE_COLORS[theme][None])
    letter = result.letter or "?"
    main = criteria_text(result.yes_count, result.answered_count)
    # Précisions éventuelles de la note (« sous-performance », « INCOMPLÈTE »), sans répéter la lettre.
    extra = grade_title(result).removeprefix(letter).strip(" ()—")
    extra_html = f"<div class='sg-grade-extra'>{html.escape(extra)}</div>" if extra else ""
    dots = "".join(f"<span class='{ANSWER_CLASSES[q.answer]}'></span>" for q in result.questions)
    st.markdown(
        f"<div class='sg-grade' style='--sg-grade:{color}'>"
        f"<div class='sg-ring' aria-label='Note {letter}'>{letter}</div>"
        f"<div><div class='sg-eyebrow'>Note</div><div class='sg-grade-main'>{main}</div>"
        f"{extra_html}<div class='sg-dots' title='Oui = point plein'>{dots}</div></div></div>",
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
        values = (
            f"{_amount(q.left.value, data.currency)} <span class='vs'>vs</span> "
            f"{_amount(q.right.value, data.currency)}"
        )
    periods = html.escape(compared_periods(q, data))
    # Mise en évidence quand l'exercice comparé n'est pas celui attendu (année sans données).
    if " · " in periods:
        main, warn = periods.split(" · ", 1)
        periods = f"{main} · <span class='sg-warn'>{warn}</span>"
    icon_html = (
        f"<span class='sg-mark {ANSWER_CLASSES[q.answer]}'>{ANSWER_ICONS[q.answer]}</span>"
        f"<small>{ANSWER_LABELS[q.answer]}</small>"
    )
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
    st.markdown(f"<div class='sg-list'>{items}</div><div class='sg-hint'>{HINT}</div>", unsafe_allow_html=True)


def render_earnings(data: FinancialData, today: date) -> None:
    earnings = describe_earnings(data.next_earnings, today)
    if earnings is None:
        st.markdown(
            "<div class='sg-muted'>Date des prochains résultats non communiquée par Yahoo Finance.</div>",
            unsafe_allow_html=True,
        )
        return
    text, days = earnings
    countdown = "aujourd'hui" if days == 0 else f"{days} j"
    st.markdown(
        "<div class='sg-card'><div><div class='sg-title'>Prochains résultats</div>"
        f"<div class='sg-sub'>{html.escape(text)}</div></div>"
        f"<div class='sg-days' title='Nombre de jours restants'>{countdown}</div></div>",
        unsafe_allow_html=True,
    )


def report_link(ticker: str | None = None) -> str | None:
    """Lien de signalement ; pour un e-mail, l'objet mentionne le ticker consulté."""
    if not LIEN_SIGNALEMENT:
        return None
    if LIEN_SIGNALEMENT.startswith("mailto:") and ticker:
        return f"{LIEN_SIGNALEMENT}?subject={quote(f'{APP_NAME} : problème avec {ticker}')}"
    return LIEN_SIGNALEMENT


def _show_ticker(ticker: str) -> None:
    st.session_state["ticker_input"] = ticker
    st.query_params["ticker"] = ticker


def _submit_search() -> None:
    """Appelé au clic sur « Noter », avant la réexécution de la page."""
    query = st.session_state["ticker_input"].strip()
    st.session_state.pop("choices", None)
    st.session_state.pop("not_found", None)
    if not query:
        st.query_params.pop("ticker", None)
        return
    try:
        matches = search_companies(query)
    except DataSourceError:
        matches = []  # recherche indisponible : le texte sera essayé comme symbole
    ticker, choices = resolve_search(query, matches)
    if ticker:
        _show_ticker(ticker)
        return
    st.query_params.pop("ticker", None)
    if choices:
        st.session_state["choices"] = (query, choices)
    else:
        st.session_state["not_found"] = query


def _choose(symbol: str) -> None:
    st.session_state.pop("choices", None)
    _show_ticker(symbol)


LEAD = (
    "La santé financière d’une entreprise notée de A à F, à partir de 5 questions "
    "sur son chiffre d’affaires et son Free Cash Flow. Données Yahoo Finance."
)


def render_header(theme: str, compact: bool) -> None:
    """Logo, marque, titre et phrase d'introduction, centrés les uns sous les autres
    (réduits au-dessus d'un résultat pour que la note reste visible sur téléphone)."""
    logo = logo_data_uri(theme)
    logo_html = f"<img src='{logo}' alt='Logo {BRAND}'>" if logo else ""
    lead = "" if compact else f"<p class='sg-lead'>{html.escape(LEAD)}</p>"
    st.markdown(
        f"<div class='sg-brand{' compact' if compact else ''}'>{logo_html}"
        f"<div class='sg-wordmark'>{BRAND}</div><div class='sg-h1'>{APP_NAME}</div>"
        f"{lead}</div>",
        unsafe_allow_html=True,
    )


def render_intro(compact: bool) -> None:
    if compact:
        st.markdown(f"<p class='sg-lead' style='margin:0'>{html.escape(LEAD)}</p>", unsafe_allow_html=True)
    st.markdown(f"<div class='sg-disclaimer'>{html.escape(DISCLAIMER)}</div>", unsafe_allow_html=True)


def render_choices(query: str, choices: list[CompanyMatch]) -> None:
    st.markdown(f"**Plusieurs sociétés correspondent à « {_escape_md(query)} »** : choisissez-en une.")
    for match in choices:
        st.button(
            choice_label(match),
            key=f"choix_{match.symbol}",
            on_click=_choose,
            args=(match.symbol,),
            use_container_width=True,
        )
    st.caption("La même société peut être cotée sur plusieurs bourses : la bourse est indiquée entre parenthèses.")


def main() -> None:
    st.set_page_config(page_title=f"{APP_NAME} · {BRAND}", page_icon=_page_icon(), layout="centered")
    theme = theme_type()
    st.markdown(CSS + theme_css(theme), unsafe_allow_html=True)

    # Le ticker courant vit dans l'URL (?ticker=AAPL) : lien partageable, et le
    # résultat reste affiché lors des réexécutions (ex. bouton « Actualiser »).
    current = st.query_params.get("ticker", "")
    choices = st.session_state.get("choices")
    not_found = st.session_state.get("not_found")
    # Page d'accueil : présentation en haut. Dès qu'un résultat est affiché, elle passe
    # sous le résultat pour que la note soit visible sans défiler (téléphone).
    showing = bool(current or choices or not_found)
    render_header(theme, compact=showing)
    if not showing:
        render_intro(compact=False)

    # Le champ a une clé fixe : s'il était recréé avec une nouvelle valeur par défaut à
    # chaque recherche, Streamlit le traiterait comme un nouveau champ et perdrait la
    # saisie (il fallait alors chercher deux fois).
    if "ticker_input" not in st.session_state:
        st.session_state["ticker_input"] = current
    with st.form("recherche"):
        st.text_input("Société ou symbole", key="ticker_input", placeholder="ex. Netflix, LVMH, AAPL, MC.PA")
        st.form_submit_button("Noter", type="primary", on_click=_submit_search)

    if choices:
        render_choices(*choices)
    elif not_found:
        st.warning(
            f"Aucune société trouvée pour « {not_found} ». Vérifiez l'orthographe ou saisissez "
            "le symbole Yahoo Finance (ex. MC.PA pour LVMH)."
        )
    elif not current:
        st.caption(
            "Saisissez le nom d'une société (ex. Netflix) ou son symbole Yahoo Finance "
            "(ex. NFLX ; suffixe .PA pour Paris, .DE pour Francfort, etc.)."
        )
    else:
        render_result(current, theme)
    if showing:
        st.divider()
        render_intro(compact=True)


def _page_icon() -> str:
    path = ASSETS / "logo_clair.png"
    return str(path) if path.exists() else "📈"


def render_result(current: str, theme: str = "light") -> None:
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
    if data.company_name:
        st.subheader(f"{_escape_md(data.company_name)} `{data.ticker}`")
    else:
        st.subheader(f"`{data.ticker}`")
        st.caption("Nom de la société non communiqué par Yahoo Finance.")
    render_grade(result, theme)
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
        st.markdown(f"Un résultat vous semble faux ? [Signaler un problème]({link})")
    if button_col.button("Actualiser", help="Ignorer le cache et interroger de nouveau Yahoo Finance"):
        fetch_data.clear(current)
        st.rerun()


main()
