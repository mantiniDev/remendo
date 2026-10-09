"""Carrega deputados (API da Câmara) e senadores em exercício (Dados Abertos do Senado)."""
import os
import requests
from .common import Execucao, agora, db, get_json, log, norm, pick

CAMARA = "https://dadosabertos.camara.leg.br/api/v2/deputados"
SENADO = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"
SENADO_LEG = "https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/{}"
# Legislaturas a carregar além dos "em exercício": inclui quem se licenciou ou saiu (suplentes, ministros etc.).
LEGISLATURAS = os.environ.get("REMENDO_LEGISLATURAS", "57").split()  # 57 = 2023-2027


def _upsert(con, id_, casa, nome, civil, partido, uf):
    con.execute(
        """INSERT INTO parlamentares(id,casa,nome,nome_norm,nome_civil_norm,partido,uf,atualizado_em)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET casa=excluded.casa,nome=excluded.nome,nome_norm=excluded.nome_norm,
             nome_civil_norm=excluded.nome_civil_norm,partido=excluded.partido,uf=excluded.uf,atualizado_em=excluded.atualizado_em""",
        (id_, casa, nome, norm(nome), norm(civil), partido, uf, agora()))


def camara(con):
    with Execucao(con, "camara") as ex:
        # primeiro as legislaturas (todos que exerceram), por último os atuais (partido/UF mais recentes)
        for leg in LEGISLATURAS + [None]:
            pagina = 1
            while True:
                params = {"itens": 100, "pagina": pagina, "ordem": "ASC", "ordenarPor": "nome"}
                if leg:
                    params["idLegislatura"] = leg
                try:
                    r = get_json(CAMARA, params)
                except (requests.RequestException, RuntimeError) as e:
                    if leg is None:
                        raise
                    log(f"AVISO: legislatura {leg} da Câmara indisponível ({e}); seguindo só com os atuais.")
                    break
                dados = r.get("dados", [])
                for d in dados:
                    _upsert(con, f"C-{d['id']}", "Câmara", d.get("nome"), d.get("nome"), d.get("siglaPartido"), d.get("siglaUf"))
                    ex.n += 1
                if len(dados) < 100:
                    break
                pagina += 1


def _lista_senadores(obj):
    """Acha a lista 'Parlamentar' em qualquer nível do JSON do Senado (o formato varia entre endpoints)."""
    if isinstance(obj, dict):
        if "Parlamentar" in obj:
            v = obj["Parlamentar"]
            return v if isinstance(v, list) else [v]
        for v in obj.values():
            r = _lista_senadores(v)
            if r:
                return r
    return []


def senado(con):
    with Execucao(con, "senado") as ex:
        for url in [SENADO_LEG.format(l) for l in LEGISLATURAS] + [SENADO]:
            try:
                r = get_json(url, headers={"Accept": "application/json"})
                lista = _lista_senadores(r)
            except (requests.RequestException, RuntimeError, ValueError) as e:
                if url == SENADO:
                    raise
                log(f"AVISO: {url} indisponível ({e}); seguindo só com os atuais.")
                continue
            for p in lista:
                i = p["IdentificacaoParlamentar"]
                _upsert(con, f"S-{i['CodigoParlamentar']}", "Senado", i.get("NomeParlamentar"),
                        pick(i, "NomeCompletoParlamentar", "NomeParlamentar"),
                        i.get("SiglaPartidoParlamentar"), i.get("UfParlamentar"))
                ex.n += 1


def run():
    con = db()
    camara(con); con.commit()
    senado(con); con.commit()
    print("Parlamentares atualizados.")
