"""Carrega deputados (API da Câmara) e senadores em exercício (Dados Abertos do Senado)."""
from .common import Execucao, agora, db, get_json, norm, pick

CAMARA = "https://dadosabertos.camara.leg.br/api/v2/deputados"
SENADO = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"


def _upsert(con, id_, casa, nome, civil, partido, uf):
    con.execute(
        """INSERT INTO parlamentares(id,casa,nome,nome_norm,nome_civil_norm,partido,uf,atualizado_em)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET casa=excluded.casa,nome=excluded.nome,nome_norm=excluded.nome_norm,
             nome_civil_norm=excluded.nome_civil_norm,partido=excluded.partido,uf=excluded.uf,atualizado_em=excluded.atualizado_em""",
        (id_, casa, nome, norm(nome), norm(civil), partido, uf, agora()))


def camara(con):
    with Execucao(con, "camara") as ex:
        pagina = 1
        while True:
            r = get_json(CAMARA, {"itens": 100, "pagina": pagina, "ordem": "ASC", "ordenarPor": "nome"})
            dados = r.get("dados", [])
            for d in dados:
                _upsert(con, f"C-{d['id']}", "Câmara", d.get("nome"), d.get("nome"), d.get("siglaPartido"), d.get("siglaUf"))
                ex.n += 1
            if len(dados) < 100:
                break
            pagina += 1


def senado(con):
    with Execucao(con, "senado") as ex:
        r = get_json(SENADO, headers={"Accept": "application/json"})
        lista = r["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
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
