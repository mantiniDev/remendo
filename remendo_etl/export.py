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


_CNES = re.compile(r"\bCNES\s*:?\s*(\d{7})\b")
# "..., DA SENADORA ELIZIANE GAMA-RP8." / "DO DEPUTADO FULANO DE TAL, ..." (texto livre da observação do empenho)
_INDICACAO = re.compile(r"\b(?:D|PEL)[OA]S?\s+(?:DEPUTAD[OA]S?(?:\s+FEDERA(?:L|IS))?|SENADOR(?:A|ES)?|DEP\.?|SEN\.?)\s+"
                        r"([A-Z][A-Z' ]{2,60}?)(?=\s*(?:-|,|\.|;|\(|/|\bRP\s*\d|\bPROCESSO\b|$))")


def natureza(modalidade):
    """Agrupa a modalidade de aplicação: entidade privada, aplicação direta (contratos da União) ou ente público."""
    m = norm(modalidade or "")
    if "PRIVAD" in m:
        return "privada"
    if m.startswith("90") or "APLICAC" in m and "DIRETA" in m:
        return "direta"
    return "publica" if m else None


def favorecidos_por_emenda(con):
    """{codigo_base: {"f": [...], "cnes": [...], "ind": {...}}} a partir dos empenhos detalhados.
    O peso de cada favorecido é o valor dos seus empenhos (reforços somam, anulações subtraem)."""
    out = {}
    for r in con.execute("""SELECT emenda_codigo, cnpj, nome, uf, modalidade,
              SUM(CASE WHEN especie LIKE 'Anula%' THEN -valor ELSE valor END) AS valor
            FROM favorecidos WHERE erro IS NULL AND cnpj IS NOT NULL AND intermediario = 0
            GROUP BY emenda_codigo, cnpj ORDER BY emenda_codigo, valor DESC"""):
        out.setdefault(r["emenda_codigo"], {"f": []})["f"].append(
            {"cnpj": r["cnpj"], "nome": r["nome"], "uf": r["uf"], "modalidade": r["modalidade"],
             "natureza": natureza(r["modalidade"]), "valor": REAIS(r["valor"])})
    cat = {r["codigo"]: r["categoria"] for r in con.execute("SELECT codigo, categoria FROM v_emendas WHERE codigo NOT LIKE '%~%'")}
    for r in con.execute("SELECT emenda_codigo, observacao FROM favorecidos WHERE observacao IS NOT NULL ORDER BY data"):
        obs = norm(r["observacao"])
        d = out.get(r["emenda_codigo"])
        if d is None:
            continue
        for c in _CNES.findall(obs):
            if c not in d.setdefault("cnes", []):
                d["cnes"].append(c)
        # quem indicou: só faz sentido onde não há autor individual (comissão, bancada, relator)
        if "ind" not in d and cat.get(r["emenda_codigo"]) not in (None, "individual"):
            m = _INDICACAO.search(obs)
            if m:
                texto = " ".join(m.group(1).split())
                _, ids = _em.candidatos(con, texto)
                d["ind"] = {"texto": texto}
                if len(ids) == 1:
                    d["ind"]["id"] = next(iter(ids))
    return out


def _partes(fav, empenhado, pago):
    """Divide empenhado e pago de uma emenda entre seus favorecidos, na proporção dos empenhos."""
    total = sum(max(0, f["valor"]) for f in fav)
    for f in fav:
        peso = max(0, f["valor"]) / total if total > 0 else 1 / len(fav)
        yield f, empenhado * peso, pago * peso


def rotulo_tipo(t):
    """'COMBUSTÍVEIS E LUBRIFICANTES.' -> 'Combustíveis e lubrificantes'; corta o detalhamento longo do Senado."""
    t = (t or "").strip()
    if not t or t == "None":
        return "Não informado"
    for corte in (", compreendendo", ", inclusive"):
        t = t.split(corte)[0]
    t = t.strip().rstrip(".").strip()
    if t.isupper():
        t = t.capitalize()
        for sigla in ("SIGEPA", "RPA"):
            t = re.sub(rf"\b{sigla.lower()}\b", sigla, t)
    return t


URL_CAMARA = "https://www.camara.leg.br/cota-parlamentar/"


def _url_doc(u):
    return (u if u.startswith("http") else URL_CAMARA + u) if u else None


def exporta_cota(con, anos):
    """cota_{ano}.json: por parlamentar (mês, tipo, maiores fornecedores) e maiores fornecedores do ano."""
    nomes = {r["id"]: dict(r) for r in con.execute("SELECT id, nome, partido, uf, casa FROM parlamentares")}
    for ano in anos:
        P = {}
        for r in con.execute("SELECT parlamentar_id, MAX(nome) AS nome, MAX(casa) AS casa, mes, SUM(valor) AS v, COUNT(*) AS n "
                             "FROM cota WHERE ano=? GROUP BY parlamentar_id, mes", (ano,)):
            info = nomes.get(r["parlamentar_id"], {})
            p = P.setdefault(r["parlamentar_id"], {"nome": info.get("nome") or r["nome"], "partido": info.get("partido"),
                                                   "uf": info.get("uf"), "casa": r["casa"], "total": 0, "n": 0,
                                                   "meses": [0] * 12, "tipos": {}, "fornecedores": []})
            if 1 <= r["mes"] <= 12:
                p["meses"][r["mes"] - 1] = REAIS(r["v"])
            p["total"] += r["v"]; p["n"] += r["n"]
        for r in con.execute("SELECT parlamentar_id, tipo, SUM(valor) AS v FROM cota WHERE ano=? GROUP BY parlamentar_id, tipo", (ano,)):
            t = P[r["parlamentar_id"]]["tipos"]
            k = rotulo_tipo(r["tipo"])
            t[k] = round(t.get(k, 0) + REAIS(r["v"]), 2)
        forn = {}
        for r in con.execute("SELECT parlamentar_id, cnpj, MAX(fornecedor) AS nome, SUM(valor) AS v, COUNT(*) AS n FROM cota "
                             "WHERE ano=? GROUP BY parlamentar_id, cnpj", (ano,)):
            forn.setdefault(r["parlamentar_id"], []).append({"cnpj": r["cnpj"], "nome": r["nome"], "valor": REAIS(r["v"]), "n": r["n"]})
        for pid, lista in forn.items():
            P[pid]["fornecedores"] = sorted(lista, key=lambda f: -f["valor"])[:15]
        for p in P.values():
            p["total"] = REAIS(p["total"])
        top = [{"cnpj": r["cnpj"], "nome": r["nome"], "valor": REAIS(r["v"]), "n": r["n"], "parlamentares": r["p"]}
               for r in con.execute("SELECT cnpj, MAX(fornecedor) AS nome, SUM(valor) AS v, COUNT(*) AS n, COUNT(DISTINCT parlamentar_id) AS p "
                                    "FROM cota WHERE ano=? AND cnpj <> '' GROUP BY cnpj ORDER BY SUM(valor) DESC LIMIT 300", (ano,))]
        tipos = {}
        for r in con.execute("SELECT casa, tipo, SUM(valor) AS v FROM cota WHERE ano=? GROUP BY casa, tipo", (ano,)):
            k = (r["casa"], rotulo_tipo(r["tipo"]))
            tipos[k] = tipos.get(k, 0) + r["v"]
        dados = {"ano": ano, "parlamentares": P, "fornecedores": top,
                 "tipos": [{"casa": c, "tipo": t, "valor": REAIS(v)} for (c, t), v in sorted(tipos.items(), key=lambda kv: -kv[1])]}
        if not P:
            continue
        with open(os.path.join(SAIDA, f"cota_{ano}.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))


def exporta_cruzamento(con):
    """CNPJ que aparece como fornecedor da cota E como favorecido de emenda do MESMO parlamentar.
    Só CNPJ completo (14 dígitos), nunca nome; CPF fica de fora. Cada lado leva os documentos para conferência."""
    emendas_fav = {}
    for r in con.execute("""SELECT e.parlamentar_id, e.codigo, e.ano, f.cnpj, MAX(f.nome) AS nome,
              SUM(CASE WHEN f.especie LIKE 'Anula%' THEN -f.valor ELSE f.valor END) AS valor, MIN(f.documento) AS empenho
            FROM favorecidos f JOIN emendas e ON e.codigo = f.emenda_codigo
            WHERE e.parlamentar_id IS NOT NULL AND f.erro IS NULL AND f.intermediario = 0 AND f.cnpj IS NOT NULL
            GROUP BY e.parlamentar_id, e.codigo, f.cnpj"""):
        cnpj = re.sub(r"\D", "", r["cnpj"])
        if len(cnpj) == 14:
            emendas_fav.setdefault((r["parlamentar_id"], cnpj), []).append(
                {"codigo": r["codigo"], "ano": r["ano"], "favorecido": r["nome"], "valor": REAIS(r["valor"]), "empenho": r["empenho"]})
    saida = []
    for r in con.execute("SELECT parlamentar_id, cnpj, MAX(fornecedor) AS nome, SUM(valor) AS v, COUNT(*) AS n, MIN(ano) AS a0, MAX(ano) AS a1 "
                         "FROM cota WHERE length(cnpj) = 14 GROUP BY parlamentar_id, cnpj"):
        emds = emendas_fav.get((r["parlamentar_id"], r["cnpj"]))
        if not emds:
            continue
        docs = [{"ano": d["ano"], "data": d["data"], "valor": REAIS(d["valor"]), "documento": d["documento"], "url": _url_doc(d["url"]),
                 "tipo": rotulo_tipo(d["tipo"]), "casa": d["casa"]}
                for d in con.execute("SELECT ano, data, valor, documento, url, tipo, casa FROM cota WHERE parlamentar_id=? AND cnpj=? "
                                     "ORDER BY valor DESC LIMIT 10", (r["parlamentar_id"], r["cnpj"]))]
        saida.append({"parlamentar_id": r["parlamentar_id"], "cnpj": r["cnpj"], "fornecedor": r["nome"],
                      "cota": {"valor": REAIS(r["v"]), "n": r["n"], "anos": [r["a0"], r["a1"]], "documentos": docs},
                      "emendas": sorted(emds, key=lambda x: -x["valor"])[:10],
                      "emendas_valor": round(sum(x["valor"] for x in emds), 2), "emendas_n": len(emds)})
    with open(os.path.join(SAIDA, "cruzamento.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    return len(saida)


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
    favs = favorecidos_por_emenda(con)
    nomes_parl = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM parlamentares")}
    ranking, indicacoes, cobertura = {}, {}, {}
    for e in con.execute("SELECT codigo, ano, categoria, parlamentar_id, autor_nome, empenhado, pago FROM v_emendas"):
        base = e["codigo"].split("~")[0]
        d = favs.get(base)
        c = cobertura.setdefault(e["ano"], {"ano": e["ano"], "emendas": 0, "com_favorecido": 0, "empenhado": 0, "empenhado_com_favorecido": 0})
        c["emendas"] += 1; c["empenhado"] += e["empenhado"]
        if not d or not d["f"]:
            continue
        c["com_favorecido"] += 1; c["empenhado_com_favorecido"] += e["empenhado"]
        for f, emp, pag in _partes(d["f"], e["empenhado"], e["pago"]):
            k = (e["ano"], f["cnpj"])
            r = ranking.setdefault(k, {"ano": e["ano"], "cnpj": f["cnpj"], "nome": f["nome"], "uf": f["uf"], "natureza": f["natureza"],
                                       "n": 0, "empenhado": 0.0, "pago": 0.0, "_autores": set(), "_cat": set()})
            r["n"] += 1; r["empenhado"] += emp; r["pago"] += pag
            r["_autores"].add(e["parlamentar_id"] or e["autor_nome"]); r["_cat"].add(e["categoria"])
        ind = d.get("ind")
        if ind:
            k = (e["ano"], ind.get("id") or ind["texto"])
            r = indicacoes.setdefault(k, {"ano": e["ano"], "texto": ind["texto"], "parlamentar_id": ind.get("id"),
                                          "parlamentar_nome": nomes_parl.get(ind.get("id")), "n": 0, "empenhado": 0, "pago": 0, "_autores": set()})
            r["n"] += 1; r["empenhado"] += e["empenhado"]; r["pago"] += e["pago"]; r["_autores"].add(e["autor_nome"])
    lista = []
    for ano in anos:
        do_ano = sorted((r for r in ranking.values() if r["ano"] == ano), key=lambda r: -r["empenhado"])
        escolhidos = do_ano[:500] + [r for r in do_ano[500:] if r["natureza"] == "privada"][:500]  # privadas além do top 500
        for r in escolhidos:
            r["autores"] = len(r.pop("_autores")); r["categorias"] = sorted(c for c in r.pop("_cat") if c)
            lista.append(_fmt(r))
    ind_lista = []
    for r in sorted(indicacoes.values(), key=lambda r: (-r["ano"], -r["empenhado"])):
        r["autores"] = sorted(r.pop("_autores"))[:10]
        ind_lista.append(_fmt(r))
    cob = []
    for c in sorted(cobertura.values(), key=lambda c: -c["ano"]):
        cob.append({"ano": c["ano"], "emendas": c["emendas"], "com_favorecido": c["com_favorecido"],
                    "pct_valor": round(100 * c["empenhado_com_favorecido"] / c["empenhado"], 1) if c["empenhado"] else 0})
    out["favorecidos"] = {"ranking": lista, "indicacoes": ind_lista, "cobertura": cob}
    meta["favorecidos_pendentes"] = con.execute(
        "SELECT COUNT(DISTINCT d.codigo_doc) FROM documentos d LEFT JOIN favorecidos f ON f.documento = d.codigo_doc "
        "WHERE d.fase LIKE 'Empenho%' AND d.codigo_doc <> '' AND f.documento IS NULL").fetchone()[0]
    meta["cobertura_favorecidos"] = cob
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
        for l in linhas:
            d = favs.get(l["codigo"].split("~")[0]) or {}
            l["favorecido_cnpj"] = " | ".join(f["cnpj"] for f in d.get("f", []))
            l["favorecido_nome"] = " | ".join(f["nome"] or "" for f in d.get("f", []))
            l["indicado_por"] = (d.get("ind") or {}).get("texto", "")
        cols = list(linhas[0].keys())
        with open(os.path.join(SAIDA, f"emendas_{ano}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(linhas)
        with open(os.path.join(SAIDA, f"emendas_{ano}.json"), "w", encoding="utf-8") as f:  # compacto: o site lê este
            json.dump([{k: v for k, v in l.items() if v not in (None, "") and k not in ("favorecido_cnpj", "favorecido_nome", "indicado_por")}
                       for l in linhas], f, ensure_ascii=False, separators=(",", ":"))
        bases = {l["codigo"].split("~")[0] for l in linhas}
        with open(os.path.join(SAIDA, f"favorecidos_{ano}.json"), "w", encoding="utf-8") as f:  # lido pela página da emenda
            json.dump({b: favs[b] for b in sorted(bases) if b in favs}, f, ensure_ascii=False, separators=(",", ":"))
    destinos = [dict(ano=a, base=b, uf=u, **{k: round(v, 2) if k != "n" else v for k, v in d.items()}) for (a, b, u), d in sorted(ufs.items())]
    for l in destinos:
        l["pct_pago"] = round(min(100.0, 100 * l["pago"] / l["empenhado"]), 1) if l["empenhado"] else 0
    with open(os.path.join(SAIDA, "ufs.json"), "w", encoding="utf-8") as f:
        json.dump(destinos, f, ensure_ascii=False, indent=1)
    anos_cota = [r[0] for r in con.execute("SELECT DISTINCT ano FROM cota ORDER BY ano")]
    exporta_cota(con, anos_cota)
    n = exporta_cruzamento(con)
    print(f"Cota: {len(anos_cota)} anos exportados; cruzamento cota × emendas: {n} pares parlamentar/CNPJ")
    print(f"Exportado em {SAIDA}/")
