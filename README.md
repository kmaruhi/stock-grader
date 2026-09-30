# stock-grader

Moteur de notation d'actions (A à F) à partir du **chiffre d'affaires** et du
**Free Cash Flow** (FCF), données Yahoo Finance via `yfinance`.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Utilisation

```bash
stock-grader AAPL                 # ou : python -m stock_grader AAPL
stock-grader AAPL MSFT MC.PA      # plusieurs tickers
stock-grader AAPL --json          # sortie JSON (pratique pour comparer avec Yahoo)
```

## Les 5 questions

| # | Question |
|---|----------|
| 1 | CA TTM > plus ancien CA annuel disponible |
| 2 | CA TTM > CA annuel le plus récent |
| 3 | FCF TTM > 0 |
| 4 | FCF TTM > plus ancien FCF annuel disponible |
| 5 | FCF TTM > FCF annuel le plus récent |

Barème : 5 Oui = **A**, 4 = **B**, 3 = **C**, 2 = **D** (sous-performance), 0–1 = **F**.

Règles :
- Égalité = Non. Si le TTM est égal au dernier exercice annuel (typique juste
  après la publication du rapport annuel), une note l'explique.
- « Plus ancien disponible » = le plus ancien exercice qui a réellement des données
  (les années vides sont ignorées ; idem pour « le plus récent », avec une note).
- Comparaison impossible → **N/A**, la note est marquée **INCOMPLÈTE** ; un N/A
  n'est pas compté comme Non (la lettre repose sur le nombre de Oui).
- Les valeurs négatives sont comparées numériquement (−50 M > −100 M = Oui).

## Provenance des chiffres (pour comparer avec Yahoo)

- CA : ligne `Total Revenue` (onglet *Financials → Income Statement*).
- FCF : ligne `Free Cash Flow` (onglet *Cash Flow*). Si absente, recalculée
  comme `Operating Cash Flow + Capital Expenditure` (signalé dans les notes).
- TTM : colonne *TTM* de Yahoo ; à défaut, somme des 4 derniers trimestres
  (uniquement si les 4 sont renseignés, signalé dans les notes).
- L'exercice affiché est l'année de la date de clôture (ex. clôture 28/09/2024 → 2024).

## Architecture

```
stock_grader/
  models.py          structures neutres (DataPoint, MetricHistory, FinancialData)
  sources/base.py    interface FinancialDataSource (fetch(ticker) -> FinancialData)
  sources/yahoo.py   implémentation yfinance
  grading.py         logique de notation pure (aucun accès réseau)
  report.py          affichage texte / JSON en français
  cli.py             ligne de commande
```

Pour changer de fournisseur de données, écrire une classe avec une méthode
`fetch(ticker) -> FinancialData` et la passer à `cli.main(source=...)`.

## Tests

```bash
pytest
```
Les tests n'accèdent pas au réseau (faux objets `Ticker`).
