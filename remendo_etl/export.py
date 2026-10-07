"""Gera os arquivos que o site consome (JSON) e os downloads da página Dados abertos (CSV)."""
import csv, json, os
from .common import agora, db

SAIDA = os.environ.get("REMENDO_SAIDA", "saida")
REAIS = lambda c: round((c or 0) / 100, 2)


def _linhas(con, sql, *a):
    return [dict(r) for r in con.execute(sql, a)]


def _fmt(l):
    for k in ("empenhado", "liquidado", "pago", "resto_pago"):
        if k in l:
            l[k] = REAIS(l[k])
    if l.get("empenhado"):
        l["pct_pago"] = round(100 * l["pago"] / l["empenhado"], 1)
    return l


def run():
    con = db()
    os.makedirs(SAIDA, exist_ok=True)
    agg = "COUNT(*) AS n, SUM(empenhado) AS empenhado, SUM(liquidado) AS liquidado, SUM(pago) AS pago"

    out = {
        "resumo": _linhas(con, f"SELECT ano, {agg} FROM v_emendas GROUP BY ano ORDER BY ano DESC"),
        "areas": _linhas(con, f"SELECT ano, COALESCE(funcao,'Não informada') AS funcao, {agg} FROM v_emendas GROUP BY ano, funcao"),
        "partidos": _linhas(con, f"SELECT ano, partido, COUNT(DISTINCT parlamentar_id) AS parlamentares, {agg} FROM v_emendas WHERE partido IS NOT NULL GROUP BY ano, partido ORDER BY partido"),
        "parlamentares": _linhas(con, f"""SELECT p.id, p.nome, p.partido, p.uf, p.casa, e.ano, {agg.replace('COUNT(*)','COUNT(e.codigo)').replace('SUM(','SUM(e.')},
              SUM(e.status='parada') AS paradas FROM parlamentares p JOIN v_emendas e ON e.parlamentar_id=p.id GROUP BY p.id, e.ano"""),
        "rankings": {
            "mais_empenham": _linhas(con, f"SELECT ano, parlamentar_id, autor_nome, partido, uf, {agg} FROM v_emendas WHERE parlamentar_id IS NOT NULL GROUP BY ano, parlamentar_id ORDER BY empenhado DESC LIMIT 100"),
            "menos_executam": _linhas(con, f"SELECT ano, parlamentar_id, autor_nome, partido, uf, {agg} FROM v_emendas WHERE parlamentar_id IS NOT NULL GROUP BY ano, parlamentar_id HAVING SUM(empenhado) > 0 ORDER BY 1.0*SUM(pago)/SUM(empenhado) ASC LIMIT 100"),
            "paradas": _linhas(con, "SELECT codigo, ano, autor_nome, partido, uf, localidade, funcao, empenhado, pago, ultima_mov FROM v_emendas WHERE status='parada' ORDER BY empenhado DESC LIMIT 200"),
        },
    }
    for chave in ("resumo", "areas", "partidos", "parlamentares"):
        out[chave] = [_fmt(l) for l in out[chave]]
    for k, v in out["rankings"].items():
        out["rankings"][k] = [_fmt(l) for l in v]

    meta = {"atualizado_em": agora(),
            "fontes": ["Portal da Transparência (CGU)", "API de Dados Abertos da Câmara", "Dados Abertos do Senado"],
            "ultimas_cargas": _linhas(con, "SELECT fonte, fim, registros, status FROM etl_runs WHERE status='ok' ORDER BY id DESC LIMIT 6")}
    out["meta"] = meta
    for chave, dados in out.items():
        with open(os.path.join(SAIDA, f"{chave}.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)

    for ano in [r["ano"] for r in con.execute("SELECT DISTINCT ano FROM emendas ORDER BY ano")]:
        linhas = [_fmt(l) for l in _linhas(con, "SELECT codigo,ano,numero,tipo,autor_nome,partido,uf,localidade,funcao,subfuncao,empenhado,liquidado,pago,resto_pago,status,ultima_mov FROM v_emendas WHERE ano=?", ano)]
        if linhas:
            cols = list(linhas[0].keys())
            with open(os.path.join(SAIDA, f"emendas_{ano}.csv"), "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols + [c for c in ("pct_pago",) if c not in cols], extrasaction="ignore")
                w.writeheader(); w.writerows(linhas)
    print(f"Exportado em {SAIDA}/")
