"""Interface en ligne de commande : python -m stock_grader AAPL MSFT ..."""

from __future__ import annotations

import argparse
import json
import sys

from .grading import grade
from .report import format_text, to_dict
from .sources import DataSourceError, FinancialDataSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-grader",
        description=(
            "Note une action de A à F selon l'évolution de son chiffre d'affaires "
            "et de son Free Cash Flow (données Yahoo Finance)."
        ),
    )
    parser.add_argument("tickers", nargs="+", metavar="TICKER", help="un ou plusieurs symboles (ex. AAPL MC.PA)")
    parser.add_argument("--json", action="store_true", help="sortie au format JSON")
    return parser


def main(argv: list[str] | None = None, source: FinancialDataSource | None = None) -> int:
    args = build_parser().parse_args(argv)
    if source is None:
        from .sources.yahoo import YFinanceDataSource

        source = YFinanceDataSource()

    results, errors = [], 0
    for ticker in args.tickers:
        try:
            result = grade(source.fetch(ticker))
        except DataSourceError as exc:
            errors += 1
            print(f"Erreur : {exc}", file=sys.stderr)
            continue
        if args.json:
            results.append(to_dict(result))
        else:
            print(format_text(result))
            print()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if errors else 0
