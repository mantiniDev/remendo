"""Uso: python -m remendo_etl.run [--anos 2023 2024] [--sem-documentos] [--max-minutos 300]"""
import argparse, datetime as dt, time
from . import emendas, export, parlamentares


def main():
    ano = dt.date.today().year
    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", type=int, nargs="+", default=[ano - 2, ano - 1, ano])
    ap.add_argument("--sem-documentos", action="store_true")
    ap.add_argument("--max-minutos", type=float, default=0,
                    help="para a carga de documentos sozinho após N minutos e segue para a exportação (0 = sem limite)")
    a = ap.parse_args()
    limite = time.monotonic() + a.max_minutos * 60 if a.max_minutos else None
    parlamentares.run()
    emendas.run(a.anos, com_documentos=not a.sem_documentos, limite=limite)
    export.run()


if __name__ == "__main__":
    main()
