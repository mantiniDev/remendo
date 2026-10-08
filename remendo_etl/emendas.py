"""Carrega emendas e seus documentos (empenho, liquidação, pagamento) do Portal da Transparência."""
import hashlib, json, os, sys, time
import requests
from .common import Execucao, agora, centavos, data_iso, db, get_json, log, norm, pick

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
# Segundos entre chamadas. A API informa ~90 chamadas/min; com ~0,5 s de latência, 0,25 s fica abaixo disso.
PAUSA = float(os.environ.get("RATE_PAUSA", "0.25"))


def _headers():
    chave = os.environ.get("PORTAL_API_KEY")
    if not chave:
        sys.exit("Defina PORTAL_API_KEY (chave gratuita do Portal da Transparência).")
    return {"chave-api-dados": chave, "Accept": "application/json"}


def paginas(caminho, params=None):
    p = 1
    while True:
        try:
            linhas = get_json(f"{BASE}{caminho}", {**(params or {}), "pagina": p}, _headers(), pausa=PAUSA)
        except requests.HTTPError as e:
            if p > 1 and e.response is not None and e.response.status_code == 400:
                log(f"AVISO: HTTP 400 na página {p} de {caminho} {params}; tratando como fim dos dados. "
                    f"Resposta: {e.response.text[:300]!r}")
                return
            raise
        if not linhas:
            return
        yield from linhas
        p += 1


def achar_parlamentar(con, autor_norm):
    if not autor_norm:
        return None
    r = con.execute("SELECT id FROM parlamentares WHERE nome_norm=? OR nome_civil_norm=?", (autor_norm, autor_norm)).fetchall()
    return r[0]["id"] if len(r) == 1 else None  # ambíguo ou ausente: fica sem vínculo


def upsert_emenda(con, d):
    """Retorna True se a emenda é nova ou mudou de valores."""
    codigo = str(pick(d, "codigoEmenda", "codigo"))
    autor = pick(d, "nomeAutor", "autor", default="")
    vals = dict(
        empenhado=centavos(pick(d, "valorEmpenhado")), liquidado=centavos(pick(d, "valorLiquidado")),
        pago=centavos(pick(d, "valorPago")) + centavos(pick(d, "valorRestoPago")),  # pago inclui restos a pagar pagos
        resto_pago=centavos(pick(d, "valorRestoPago")))
    h = hashlib.sha1(json.dumps(vals, sort_keys=True).encode()).hexdigest()
    antigo = con.execute("SELECT hash FROM emendas WHERE codigo=?", (codigo,)).fetchone()
    con.execute(
        """INSERT INTO emendas(codigo,ano,numero,tipo,autor_nome,autor_norm,parlamentar_id,localidade,funcao,subfuncao,
             empenhado,liquidado,pago,resto_pago,hash,raw,atualizado_em)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(codigo) DO UPDATE SET ano=excluded.ano,numero=excluded.numero,tipo=excluded.tipo,
             autor_nome=excluded.autor_nome,autor_norm=excluded.autor_norm,parlamentar_id=excluded.parlamentar_id,
             localidade=excluded.localidade,funcao=excluded.funcao,subfuncao=excluded.subfuncao,
             empenhado=excluded.empenhado,liquidado=excluded.liquidado,pago=excluded.pago,resto_pago=excluded.resto_pago,
             hash=excluded.hash,raw=excluded.raw,atualizado_em=excluded.atualizado_em""",
        (codigo, pick(d, "ano"), str(pick(d, "numeroEmenda", default="")), pick(d, "tipoEmenda"),
         autor, norm(autor), achar_parlamentar(con, norm(autor)),
         pick(d, "localidadeDoGasto", "localidade"), pick(d, "funcao"), pick(d, "subfuncao"),
         vals["empenhado"], vals["liquidado"], vals["pago"], vals["resto_pago"], h,
         json.dumps(d, ensure_ascii=False), agora()))
    return antigo is None or antigo["hash"] != h


def carregar_documentos(con, codigo):
    for d in paginas(f"/emendas/documentos/{codigo}"):
        con.execute(
            """INSERT OR IGNORE INTO documentos(emenda_codigo,codigo_doc,data,fase,especie,valor,raw) VALUES(?,?,?,?,?,?,?)""",
            (codigo, str(pick(d, "codigoDocumento", "codigoDocumentoResumido", default="")),
             data_iso(pick(d, "data", "dataDocumento")), str(pick(d, "fase", default="")),
             pick(d, "especieTipo", "especie"), centavos(pick(d, "valor", "valorDocumento")),
             json.dumps(d, ensure_ascii=False)))
    # só marca como concluída depois de baixar todas as páginas
    con.execute("INSERT OR REPLACE INTO docs_carregados(codigo, hash) SELECT codigo, hash FROM emendas WHERE codigo=?", (codigo,))


def _semear(con):
    """Cargas antigas (sem a tabela de controle): considera concluídas as emendas que já têm documentos.
    Roda ANTES de listar as emendas, para o hash ainda ser o da carga anterior."""
    if con.execute("SELECT COUNT(*) FROM docs_carregados").fetchone()[0] == 0:
        con.execute("INSERT OR IGNORE INTO docs_carregados(codigo, hash) "
                    "SELECT DISTINCT d.emenda_codigo, e.hash FROM documentos d JOIN emendas e ON e.codigo = d.emenda_codigo")


def carregar_pendentes(con, anos, limite):
    marcas = ",".join("?" * len(anos))
    fila = [r["codigo"] for r in con.execute(
        f"""SELECT e.codigo FROM emendas e LEFT JOIN docs_carregados c ON c.codigo = e.codigo
            WHERE e.ano IN ({marcas}) AND e.empenhado > 0 AND (c.hash IS NULL OR c.hash <> e.hash)
            ORDER BY e.ano DESC, e.empenhado DESC""", anos)]
    log(f"Emendas com documentos a baixar: {len(fila)} (mais recentes e de maior valor primeiro)")
    t0, seguidas = time.monotonic(), 0
    for i, cod in enumerate(fila, 1):
        if limite and time.monotonic() >= limite:
            log(f"Tempo máximo atingido: {i - 1} de {len(fila)} emendas nesta execução; o restante continua na próxima.")
            break
        try:
            carregar_documentos(con, cod)
            seguidas = 0
        except (requests.RequestException, RuntimeError) as e:
            seguidas += 1
            log(f"AVISO: documentos da emenda {cod} falharam ({e}); ficam para a próxima execução.")
            if seguidas >= 20:
                log("20 falhas seguidas; interrompendo a carga de documentos.")
                break
            continue
        if i % 50 == 0:
            con.commit()
            log(f"  documentos: {i}/{len(fila)} emendas ({(time.monotonic() - t0) / 60:.0f} min)")
    con.commit()


def run(anos, com_documentos=True, limite=None):
    """limite: instante (time.monotonic) em que a carga de documentos deve parar sozinha."""
    con = db()
    _semear(con)
    con.commit()
    with Execucao(con, "portal_emendas") as ex:
        for ano in anos:
            alteradas = 0
            for d in paginas("/emendas", {"ano": ano}):
                alteradas += upsert_emenda(con, d)
                ex.n += 1
            con.commit()
            log(f"{ano}: lista completa ({ex.n} lidas no total; {alteradas} novas ou alteradas neste ano)")
        if com_documentos:
            carregar_pendentes(con, anos, limite)
