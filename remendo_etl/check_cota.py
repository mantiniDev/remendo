"""Confere as fontes da cota parlamentar antes de escrever a carga (rode pelo workflow "Conferir campos da API").

Uso: python -m remendo_etl.check_cota [ano] [id_deputado]
Tenta cada endereço candidato e mostra: status HTTP, tipo e tamanho; para zip, os arquivos dentro; para JSON/CSV,
os campos, dois registros de exemplo, o total de linhas e algumas somas. Não grava nada.
"""
import csv, io, json, sys, zipfile
from collections import Counter
import requests

ano = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
dep = sys.argv[2] if len(sys.argv) > 2 else "220660"
S = requests.Session()
S.headers["User-Agent"] = "remendo.com.br (conferência de campos)"

CAMARA = [
    f"https://www.camara.leg.br/cotas/Ano-{ano}.json.zip",
    f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip",
    f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep}/despesas?ano={ano}&itens=3&ordem=DESC&ordenarPor=dataDocumento",
    f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep}",
]
SENADO = [
    f"https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv",
    f"https://www12.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv",
    f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}",
]


def titulo(t):
    print(f"\n{'=' * 100}\n{t}", flush=True)


def resumo_registros(regs, origem):
    """Campos, exemplos e somas de uma lista de dicionários."""
    print(f"{origem}: {len(regs)} registros")
    if not regs:
        return
    campos = list(regs[0].keys())
    print("Campos:", campos)
    for r in regs[:2]:
        print(json.dumps(r, ensure_ascii=False, indent=1)[:3000])
    # colunas que parecem identificar parlamentar, tipo de despesa, mês e valor
    for c in campos:
        cl = c.lower()
        if any(k in cl for k in ("descricao", "tipo", "despesa", "mes", "uf", "partido")) and "fornecedor" not in cl:
            vals = Counter(str(r.get(c)) for r in regs)
            if len(vals) <= 40:
                print(f"  valores de {c!r}: {vals.most_common(40)}")
        if any(k in cl for k in ("ide", "id", "senador", "parlamentar", "cpf")) and "documento" not in cl:
            print(f"  {c!r}: {len(set(str(r.get(c)) for r in regs))} valores distintos, ex.: {[r.get(c) for r in regs[:3]]}")
    for c in campos:
        if "vlr" in c.lower() or "valor" in c.lower():
            vals = [num(r.get(c)) for r in regs]
            ok = [v for v in vals if v is not None]
            print(f"  soma de {c!r}: {sum(ok):,.2f} ({sum(v < 0 for v in ok)} negativos, {len(vals) - len(ok)} não numéricos)")


def num(v):
    """'1.234,56', '1234.56' ou 1234.56 -> float; None se não for número."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def ler_csv(texto, origem):
    linhas = texto.splitlines()
    print("Primeiras 3 linhas brutas:")
    for l in linhas[:3]:
        print("  ", l[:400])
    # o CSV do Senado tem uma linha "ULTIMA ATUALIZACAO" antes do cabeçalho
    ini = 1 if linhas and "ATUALIZA" in linhas[0].upper() else 0
    sep = ";" if linhas[ini].count(";") > linhas[ini].count(",") else ","
    regs = list(csv.DictReader(io.StringIO("\n".join(linhas[ini:])), delimiter=sep))
    resumo_registros(regs, origem)


def decodifica(b):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return b.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace"), "utf-8 (com substituição)"


def examina(url):
    titulo(url)
    try:
        r = S.get(url, timeout=180, headers={"Accept": "application/json, text/csv, */*"})
    except requests.RequestException as e:
        print("ERRO de conexão:", e)
        return
    print(f"HTTP {r.status_code} | {r.headers.get('content-type')} | {len(r.content):,} bytes | final: {r.url}")
    if r.status_code >= 400:
        print(r.text[:500])
        return
    b = r.content
    if b[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(b))
        print("Arquivos no zip:", [(i.filename, i.file_size) for i in z.infolist()])
        nome = z.infolist()[0].filename
        b = z.read(nome)
        url = nome
    texto, enc = decodifica(b)
    print("Codificação:", enc)
    t = texto.lstrip()
    if t[:1] in "[{":
        try:
            d = json.loads(t)
        except ValueError as e:
            print("JSON inválido:", e, t[:500])
            return
        if isinstance(d, dict):
            print("Chaves do topo:", list(d.keys()))
            regs = d.get("dados", d)
            if isinstance(d.get("links"), list):
                print("links:", d["links"])
        else:
            regs = d
        if isinstance(regs, dict):
            print(json.dumps(regs, ensure_ascii=False, indent=1)[:4000])
        else:
            resumo_registros(regs, url)
    else:
        ler_csv(texto, url)


if __name__ == "__main__":
    titulo(f"COTA PARLAMENTAR: ano {ano}, deputado de exemplo {dep}")
    for u in CAMARA + SENADO:
        examina(u)
