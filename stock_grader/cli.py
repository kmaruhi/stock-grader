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
    parser.add_argument("tickers", nargs="*", metavar="TICKER", help="un ou plusieurs symboles (ex. AAPL MC.PA)")
    parser.add_argument("--json", action="store_true", help="sortie au format JSON")
    parser.add_argument(
        "--verifier",
        metavar="FICHIER.csv",
        help="compare les notes calculées aux notes de référence du fichier (ex. references.csv)",
    )
    return parser


def main(argv: list[str] | None = None, source: FinancialDataSource | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.tickers and not args.verifier:
        parser.error("indiquez au moins un ticker, ou --verifier FICHIER.csv")
    if source is None:
        from .sources.yahoo import YFinanceDataSource

        source = YFinanceDataSource()

    if args.verifier:
        return _verify(args.verifier, source)

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


def _verify(path: str, source: FinancialDataSource) -> int:
    from .reference import ReferenceFileError, compare, format_comparisons, load_references

    try:
        references = load_references(path)
    except ReferenceFileError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    if not references:
        print(f"Aucune note de référence dans {path}.", file=sys.stderr)
        return 2
    comparisons = compare(references, source)
    print(format_comparisons(comparisons))
    return 0 if all(c.status == "OK" for c in comparisons) else 1
