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
        l["pct_pago"] = min(100.0, round(100 * l["pago"] / l["empenhado"], 1))  # restos pagos podem passar do empenho do ano
        l["nao_pago"] = max(0, round(l["empenhado"] - l["pago"], 2))
    return l


def run():
    con = db()
    os.makedirs(SAIDA, exist_ok=True)
    agg = "COUNT(*) AS n, SUM(empenhado) AS empenhado, SUM(liquidado) AS liquidado, SUM(pago) AS pago"
    anos = [r[0] for r in con.execute("SELECT DISTINCT ano FROM emendas ORDER BY ano DESC")]
    pessoa = f"SELECT ano, parlamentar_id, autor_nome, partido, uf, casa, {agg} FROM v_emendas WHERE parlamentar_id IS NOT NULL AND ano=? AND casa=? GROUP BY ano, parlamentar_id"

    rankings = {"paradas": _linhas(con, "SELECT codigo, ano, categoria, autor_nome, partido, uf, localidade, funcao, empenhado, pago, ultima_mov FROM v_emendas WHERE status='parada' ORDER BY empenhado DESC LIMIT 200")}
    for casa, sufixo in (("Câmara", "camara"), ("Senado", "senado")):
        for ano in anos:
            rankings.setdefault(f"maior_nao_pago_{sufixo}", []).extend(
                _linhas(con, pessoa + " ORDER BY SUM(empenhado) - SUM(pago) DESC LIMIT 50", ano, casa))
            rankings.setdefault(f"menos_executam_{sufixo}", []).extend(
                _linhas(con, pessoa + " HAVING SUM(empenhado) > 0 ORDER BY 1.0*SUM(pago)/SUM(empenhado) ASC LIMIT 50", ano, casa))
    for ano in anos:  # bancadas, comissões e relator: não têm parlamentar, o autor é o grupo
        rankings.setdefault("coletivas_menos_executam", []).extend(_linhas(
            con, f"SELECT ano, categoria, autor_nome, {agg} FROM v_emendas WHERE categoria IN ('bancada','comissao','relator') AND ano=? "
                 "GROUP BY ano, categoria, autor_nome HAVING SUM(empenhado) > 0 ORDER BY 1.0*SUM(pago)/SUM(empenhado) ASC LIMIT 50", ano))

    out = {
        "resumo": _linhas(con, f"SELECT ano, {agg} FROM v_emendas GROUP BY ano ORDER BY ano DESC"),
        "categorias": _linhas(con, f"SELECT ano, categoria, {agg} FROM v_emendas GROUP BY ano, categoria ORDER BY ano DESC, SUM(empenhado) DESC"),
        "areas": _linhas(con, f"SELECT ano, COALESCE(funcao,'Não informada') AS funcao, {agg} FROM v_emendas GROUP BY ano, funcao"),
        "partidos": _linhas(con, f"SELECT ano, partido, COUNT(DISTINCT parlamentar_id) AS parlamentares, {agg} FROM v_emendas WHERE partido IS NOT NULL GROUP BY ano, partido ORDER BY partido"),
        "parlamentares": _linhas(con, f"""SELECT p.id, p.nome, p.partido, p.uf, p.casa, e.ano, {agg.replace('COUNT(*)','COUNT(e.codigo)').replace('SUM(','SUM(e.')},
              SUM(e.status='parada') AS paradas FROM parlamentares p JOIN v_emendas e ON e.parlamentar_id=p.id GROUP BY p.id, e.ano"""),
        "nao_vinculados": _linhas(con, f"SELECT ano, autor_nome, {agg} FROM v_emendas WHERE categoria='individual' AND parlamentar_id IS NULL GROUP BY ano, autor_nome ORDER BY SUM(empenhado) DESC LIMIT 300"),
        "rankings": rankings,
    }
    for chave in ("resumo", "categorias", "areas", "partidos", "parlamentares", "nao_vinculados"):
        out[chave] = [_fmt(l) for l in out[chave]]
    for k, v in out["rankings"].items():
        out["rankings"][k] = [_fmt(l) for l in v]

    # participação de cada categoria no total do ano
    totais = {r["ano"]: r["empenhado"] for r in out["resumo"]}
    for l in out["categorias"]:
        l["pct_do_total"] = round(100 * l["empenhado"] / totais[l["ano"]], 1) if totais.get(l["ano"]) else 0

    duplicados = []
    for r in _linhas(con, "SELECT codigo, ano, iguais, primeiro, repetido FROM emendas_duplicadas ORDER BY ano, codigo"):
        r["primeiro"], r["repetido"] = json.loads(r["primeiro"]), json.loads(r["repetido"])
        duplicados.append(r)
    out["duplicados"] = duplicados

    pend = con.execute("SELECT COUNT(*) FROM emendas e LEFT JOIN docs_carregados c ON c.codigo=e.codigo "
                       "WHERE e.empenhado>0 AND (c.hash IS NULL OR c.hash<>e.hash)").fetchone()[0]
    meta = {"atualizado_em": agora(),
            "fontes": ["Portal da Transparência (CGU)", "API de Dados Abertos da Câmara", "Dados Abertos do Senado"],
            "ultimas_cargas": _linhas(con, "SELECT fonte, fim, registros, status FROM etl_runs WHERE status='ok' ORDER BY id DESC LIMIT 6"),
            "emendas_sem_documentos": pend, "carga_parcial": pend > 0,
            "vinculo_individuais": _linhas(con, "SELECT ano, ROUND(100.0*SUM(CASE WHEN parlamentar_id IS NOT NULL THEN empenhado ELSE 0 END)/SUM(empenhado),1) AS pct_valor_vinculado, "
                                                "SUM(parlamentar_id IS NULL) AS emendas_sem_vinculo FROM v_emendas WHERE categoria='individual' GROUP BY ano ORDER BY ano DESC"),
            "codigos_repetidos": len(duplicados)}
    out["meta"] = meta
    for chave, dados in out.items():
        with open(os.path.join(SAIDA, f"{chave}.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)

    for ano in [r["ano"] for r in con.execute("SELECT DISTINCT ano FROM emendas ORDER BY ano")]:
        linhas = [_fmt(l) for l in _linhas(con, "SELECT codigo,ano,numero,tipo,categoria,autor_nome,partido,uf,localidade,funcao,subfuncao,empenhado,liquidado,pago,resto_pago,status,ultima_mov FROM v_emendas WHERE ano=?", ano)]
        if linhas:
            cols = list(linhas[0].keys())
            with open(os.path.join(SAIDA, f"emendas_{ano}.csv"), "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols + [c for c in ("pct_pago",) if c not in cols], extrasaction="ignore")
                w.writeheader(); w.writerows(linhas)
    print(f"Exportado em {SAIDA}/")
