"""Carrega emendas e seus documentos (empenho, liquidação, pagamento) do Portal da Transparência."""
import hashlib, json, os, sys
from .common import Execucao, agora, centavos, data_iso, db, get_json, norm, pick
import requests

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
PAUSA = float(os.environ.get("RATE_PAUSA", "0.7"))  # segundos entre chamadas


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
                print(f"AVISO: HTTP 400 na página {p} de {caminho} {params}; tratando como fim dos dados. "
                      f"Resposta: {e.response.text[:300]!r}", flush=True)
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
        pago=centavos(pick(d, "valorPago")) + centavos(pick(d, "valorRestoPago")), resto_pago=centavos(pick(d, "valorRestoPago")))
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


def run(anos, com_documentos=True):
    con = db()
    with Execucao(con, "portal_emendas") as ex:
        for ano in anos:
            mudadas = []
            for d in paginas("/emendas", {"ano": ano}):
                if upsert_emenda(con, d):
                    mudadas.append(str(pick(d, "codigoEmenda", "codigo")))
                ex.n += 1
            con.commit()
            print(f"{ano}: {ex.n} lidas acumuladas, {len(mudadas)} novas/alteradas")
            if com_documentos:
                pendentes = set(mudadas) | {r["codigo"] for r in con.execute(
                    "SELECT codigo FROM emendas WHERE ano=? AND empenhado>0 AND NOT EXISTS "
                    "(SELECT 1 FROM documentos d WHERE d.emenda_codigo=emendas.codigo)", (ano,))}
                for i, cod in enumerate(pendentes, 1):
                    carregar_documentos(con, cod)
                    if i % 50 == 0:
                        con.commit()
                con.commit()
