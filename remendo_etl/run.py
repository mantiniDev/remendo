"""Uso: python -m remendo_etl.run [--anos 2023 2024 2025] [--sem-documentos]"""
import argparse, datetime as dt
from . import emendas, export, parlamentares


def main():
    ano = dt.date.today().year
    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", type=int, nargs="+", default=[ano - 2, ano - 1, ano])
    ap.add_argument("--sem-documentos", action="store_true")
    a = ap.parse_args()
    parlamentares.run()
    emendas.run(a.anos, com_documentos=not a.sem_documentos)
    export.run()


if __name__ == "__main__":
    main()
