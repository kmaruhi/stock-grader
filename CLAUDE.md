# stock-grader — notes pour Claude

Outil pédagogique : note une action de A à F (5 questions sur le chiffre d'affaires et
le Free Cash Flow, données Yahoo Finance via yfinance). Utilisé par des élèves via un
site Streamlit Community Cloud. L'enseignante n'est pas développeuse : lui expliquer
les choses simplement, en anglais ; tout le texte visible par les élèves est en français.

## Organisation
- `main` = version du site des élèves (Streamlit Cloud déploie `main`). Ne jamais pousser
  directement sur `main` : travailler sur une branche, puis ouvrir une pull request que
  l'enseignante fusionne elle-même.
- Ne pas modifier les règles de notation (`stock_grader/grading.py`) sans demande explicite.

## Commandes
- Installer : `python -m pip install -e ".[dev]" playwright`
- Tests (hors ligne, rapides) : `python -m pytest -q`
- Noter des actions : `stock-grader HIMS S PGNY` (accès Yahoo nécessaire)
- Vérifier les notes de référence de l'enseignante : `stock-grader --verifier references.csv`
- Site en local : `streamlit run app.py`

## Accès à Yahoo Finance
Seules les sessions lancées avec l'environnement « stock-grader » peuvent joindre Yahoo
(l'environnement « Default » le bloque). Sans accès, tous les tickers répondent
« Aucune donnée financière reçue… ».

## Vérification sur données réelles
Quand une note diffère de `references.csv`, comparer chaque montant affiché avec
finance.yahoo.com (onglets Financials → Income Statement / Cash Flow, colonnes TTM et
annuelles) pour trouver la cause avant de proposer une correction, et l'expliquer à
l'enseignante question par question.
