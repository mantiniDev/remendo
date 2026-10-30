"""Cota parlamentar: CEAP dos deputados (arquivo anual da Câmara) e CEAPS dos senadores (API administrativa do Senado).

Cada ano é recarregado inteiro a cada execução (as fontes corrigem e acrescentam documentos). O vínculo é pelo id
oficial: `ideCadastro` da Câmara = id da API de Dados Abertos (C-...); `codSenador` = código do Senado (S-...).
Despesas de lideranças (sem deputado) ficam de fora.
"""
import csv, io, re, zipfile
import requests
from .common import Execucao, centavos, db, log

CAMARA = "https://www.camara.leg.br/cotas/Ano-{}.csv.zip"
SENADO = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{}"
PREFIXO_URL = "https://www.camara.leg.br/cota-parlamentar/"  # guardado sem o prefixo, para o banco não crescer à toa


def so_digitos(s):
    return re.sub(r"\D", "", s or "")


def _baixa(url):
    r = requests.get(url, timeout=300, headers={"User-Agent": "remendo.com.br"})
    r.raise_for_status()
    return r


def camara(con, ano):
    z = zipfile.ZipFile(io.BytesIO(_baixa(CAMARA.format(ano)).content))
    linhas, liderancas = [], 0
    with z.open(z.infolist()[0]) as f:
        for d in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";"):
            ide = (d.get("ideCadastro") or "").strip()
            if not ide:
                liderancas += 1
                continue
            url = (d.get("urlDocumento") or "").strip()
            linhas.append(("Câmara", ano, int(d.get("numMes") or 0), f"C-{ide}", d.get("txNomeParlamentar"),
                           d.get("txtDescricao"), d.get("txtFornecedor"), so_digitos(d.get("txtCNPJCPF")),
                           centavos(d.get("vlrLiquido")), (d.get("datEmissao") or "")[:10] or None, d.get("txtNumero"),
                           url[len(PREFIXO_URL):] if url.startswith(PREFIXO_URL) else url))
    return linhas, liderancas


def senado(con, ano):
    dados = _baixa(SENADO.format(ano)).json()
    return [("Senado", ano, int(d.get("mes") or 0), f"S-{d.get('codSenador')}", d.get("nomeSenador"),
             d.get("tipoDespesa"), d.get("fornecedor"), so_digitos(d.get("cpfCnpj")),
             centavos(d.get("valorReembolsado")), (d.get("data") or "")[:10] or None, d.get("documento"), None)
            for d in dados if d.get("codSenador")], 0


def run(anos):
    """Falha numa fonte não derruba a execução: o ano fica com os dados da carga anterior."""
    con = db()
    for casa, carga in (("Câmara", camara), ("Senado", senado)):
        with Execucao(con, f"cota_{'camara' if casa == 'Câmara' else 'senado'}") as ex:
            for ano in anos:
                try:
                    linhas, fora = carga(con, ano)
                except (requests.RequestException, zipfile.BadZipFile, ValueError, KeyError) as e:
                    log(f"AVISO: cota {casa} {ano} indisponível ({e}); mantidos os dados anteriores.")
                    continue
                con.execute("DELETE FROM cota WHERE casa=? AND ano=?", (casa, ano))
                con.executemany("INSERT INTO cota(casa,ano,mes,parlamentar_id,nome,tipo,fornecedor,cnpj,valor,data,documento,url) "
                                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", linhas)
                con.commit()
                ex.n += len(linhas)
                total = sum(l[8] for l in linhas) / 100
                sem = con.execute("SELECT COUNT(DISTINCT parlamentar_id) FROM cota WHERE casa=? AND ano=? AND parlamentar_id NOT IN "
                                  "(SELECT id FROM parlamentares)", (casa, ano)).fetchone()[0]
                log(f"Cota {casa} {ano}: {len(linhas)} documentos, R$ {total:,.2f}"
                    + (f" ({fora} de lideranças, fora)" if fora else "")
                    + (f"; AVISO: {sem} ids sem cadastro na tabela de parlamentares" if sem else ""))
