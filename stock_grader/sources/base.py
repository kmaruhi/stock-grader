"""Interface commune des sources de données.

Pour changer de fournisseur, il suffit d'écrire une classe exposant
``fetch(ticker) -> FinancialData`` ; la logique de notation n'en dépend pas.
"""

from __future__ import annotations

from typing import Protocol

from ..models import FinancialData


class DataSourceError(Exception):
    """Échec de récupération des données (réseau, ticker inconnu, etc.)."""


class FinancialDataSource(Protocol):
    def fetch(self, ticker: str) -> FinancialData: ...
