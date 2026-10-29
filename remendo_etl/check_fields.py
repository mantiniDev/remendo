"""Mostra os campos reais devolvidos pela API (rode antes da primeira carga).

Uso: python -m remendo_etl.check_fields [ano] [n_emendas]
Além de /emendas e /emendas/documentos, consulta /despesas/documentos/{codigo} para ver se o detalhe da despesa
traz o favorecido (quem recebeu), órgão e unidade gestora. Pega emendas de tipos diferentes e um documento por fase.
"""
import json, sys
import requests
from .common import get_json, log
from .emendas import BASE, PAUSA, _headers, paginas

ano = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
n_emendas = int(sys.argv[2]) if len(sys.argv) > 2 else 4


def mostra(titulo, obj):
    print(f"\n=== {titulo}\n" + json.dumps(obj, ensure_ascii=False, indent=1))


primeira = next(paginas("/emendas", {"ano": ano}))
mostra("Campos de /emendas", primeira)

# uma emenda de cada tipo (finalidade definida, transferência especial, bancada...), com valor empenhado
escolhidas, tipos = [], set()
for k, e in enumerate(paginas("/emendas", {"ano": ano})):
    if k >= 300:  # ~20 páginas: basta para achar os tipos comuns sem gastar o limite da API
        break
    tipo = e.get("tipoEmenda")
    if tipo not in tipos and str(e.get("valorEmpenhado", "0")).strip() not in ("0", "0,00"):
        tipos.add(tipo)
        escolhidas.append(e)
    if len(escolhidas) >= n_emendas:
        break

for e in escolhidas:
    codigo = e.get("codigoEmenda")
    print(f"\n##### Emenda {codigo} | {e.get('tipoEmenda')} | {e.get('nomeAutor')} | {e.get('localidadeDoGasto')}")
    docs = list(paginas(f"/emendas/documentos/{codigo}"))
    if not docs:
        print("(sem documentos)")
        continue
    mostra(f"Campos de /emendas/documentos/{codigo} (1 de {len(docs)})", docs[0])
    fases = set()
    for d in docs:
        fase = d.get("fase")
        cod_doc = d.get("codigoDocumento") or d.get("codigoDocumentoResumido")
        if fase in fases or not cod_doc:
            continue
        fases.add(fase)
        try:
            det = get_json(f"{BASE}/despesas/documentos/{cod_doc}", headers=_headers(), pausa=PAUSA)
        except (requests.HTTPError, RuntimeError) as err:
            log(f"AVISO: /despesas/documentos/{cod_doc} falhou: {err}")
            continue
        mostra(f"Campos de /despesas/documentos/{cod_doc} (fase {fase})", det)
