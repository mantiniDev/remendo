"""Gera os arquivos que o site consome (JSON) e os downloads da página Dados abertos (CSV)."""
import csv, json, os, re
from .common import agora, db, norm
from . import emendas as _em

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
    pessoa = f"SELECT ano, parlamentar_id, MAX(parlamentar_nome) AS autor_nome, partido, uf, casa, {agg} FROM v_emendas WHERE parlamentar_id IS NOT NULL AND ano=? AND casa=? GROUP BY ano, parlamentar_id"

    rankings = {"paradas": _linhas(con, "SELECT codigo, ano, categoria, autor_nome, partido, uf, localidade, funcao, empenhado, pago, ultima_mov FROM v_emendas WHERE status='parada' ORDER BY empenhado DESC LIMIT 200")}
    for casa, sufixo in (("Câmara", "camara"), ("Senado", "senado")):
        for ano in anos:
            rankings.setdefault(f"maior_nao_pago_{sufixo}", []).extend(
                _linhas(con, pessoa + " ORDER BY SUM(empenhado) - SUM(pago) DESC LIMIT 50", ano, casa))
            rankings.setdefault(f"menos_executam_{sufixo}", []).extend(
                _linhas(con, pessoa + " HAVING SUM(empenhado) >= 500000000 ORDER BY 1.0*SUM(pago)/SUM(empenhado) ASC LIMIT 50", ano, casa))  # só quem tem ao menos R$ 5 mi empenhados
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

    for l in out["nao_vinculados"]:  # por que não vinculou: nenhum candidato, ou mais de um com o mesmo nome
        metodo, ids = _em.candidatos(con, norm(l["autor_nome"]))
        l["motivo"] = "ambiguo" if len(ids) > 1 else "sem_candidato"
        if len(ids) > 1:
            l["candidatos"] = sorted(ids)

    pend = con.execute("SELECT COUNT(*) FROM emendas e LEFT JOIN docs_carregados c ON c.codigo=e.codigo "
                       "WHERE e.codigo NOT LIKE '%~%' AND e.empenhado>0 AND (c.hash IS NULL OR c.hash<>e.hash)").fetchone()[0]
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

    # datas por fase, a partir dos documentos (empenho, liquidação, pagamento) da linha-base de cada emenda
    fases = {}
    for r in con.execute("SELECT emenda_codigo, fase, MIN(data) AS ini, MAX(data) AS fim, COUNT(*) AS n FROM documentos GROUP BY emenda_codigo, fase"):
        f = norm(r["fase"])
        chave = "empenho" if f.startswith("EMPENHO") else "liquidacao" if f.startswith("LIQUID") else "pagamento" if f.startswith("PAGAMENTO") else None
        d = fases.setdefault(r["emenda_codigo"], {"n": 0})
        d["n"] += r["n"]
        if chave:
            d[chave] = (r["ini"], r["fim"])

    ufs = {}
    nomes_uf = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
                "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
                "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
                "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC",
                "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO"}

    def uf_do_destino(loc):
        l = norm(loc or "")
        m = re.search(r" - ([A-Z]{2})$", l)
        if m:
            return m.group(1)
        m = re.match(r"^(.+?)\s*\(UF\)$", l)
        if m and m.group(1) in nomes_uf:
            return nomes_uf[m.group(1)]
        return "ND"  # nacional, múltiplo ou não informado

    CAMPOS = ("codigo,ano,numero,tipo,categoria,autor_nome,parlamentar_id,parlamentar_nome,partido,uf,localidade,funcao,subfuncao,"
              "empenhado,liquidado,pago,resto_pago,status,ultima_mov")
    for ano in [r["ano"] for r in con.execute("SELECT DISTINCT ano FROM emendas ORDER BY ano")]:
        linhas = [_fmt(l) for l in _linhas(con, f"SELECT {CAMPOS} FROM v_emendas WHERE ano=?", ano)]
        if not linhas:
            continue
        for l in linhas:
            base = l["codigo"].split("~")[0]
            d = fases.get(base, {})
            l["data_empenho"] = (d.get("empenho") or (None, None))[0]
            l["data_liquidacao"] = (d.get("liquidacao") or (None, None))[1]
            l["data_pagamento"] = (d.get("pagamento") or (None, None))[1]
            l["n_documentos"] = d.get("n", 0)
            uf_autor = l.get("uf")
            if not uf_autor and l["categoria"] == "bancada":  # "BANCADA DO RIO GRANDE DO SUL" -> RS
                m = re.match(r"^BANCADA D[AEO]S?\s+(.+)$", norm(l["autor_nome"]))
                uf_autor = nomes_uf.get(m.group(1)) if m else None
            for base, uf in (("destino", uf_do_destino(l["localidade"])), ("autor", uf_autor or "ND")):
                u = ufs.setdefault((ano, base, uf), {"n": 0, "empenhado": 0.0, "liquidado": 0.0, "pago": 0.0})
                u["n"] += 1
                for k in ("empenhado", "liquidado", "pago"):
                    u[k] += l[k]
        cols = list(linhas[0].keys())
        with open(os.path.join(SAIDA, f"emendas_{ano}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(linhas)
        with open(os.path.join(SAIDA, f"emendas_{ano}.json"), "w", encoding="utf-8") as f:  # compacto: o site lê este
            json.dump([{k: v for k, v in l.items() if v not in (None, "")} for l in linhas], f, ensure_ascii=False, separators=(",", ":"))
    destinos = [dict(ano=a, base=b, uf=u, **{k: round(v, 2) if k != "n" else v for k, v in d.items()}) for (a, b, u), d in sorted(ufs.items())]
    for l in destinos:
        l["pct_pago"] = round(min(100.0, 100 * l["pago"] / l["empenhado"]), 1) if l["empenhado"] else 0
    with open(os.path.join(SAIDA, "ufs.json"), "w", encoding="utf-8") as f:
        json.dump(destinos, f, ensure_ascii=False, indent=1)
    print(f"Exportado em {SAIDA}/")
