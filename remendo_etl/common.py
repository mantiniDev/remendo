import datetime as dt, os, re, sqlite3, time, unicodedata
import requests

DB_PATH = os.environ.get("REMENDO_DB", "remendo.db")
_SESSION = requests.Session()


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())
    return c


def agora():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def centavos(v):
    """Converte '1.234,56', 1234.56 ou None em centavos (inteiro)."""
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return round(v * 100)
    s = str(v).replace("R$", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s) * 100)
    except ValueError:
        return 0


def data_iso(s):
    if not s:
        return None
    s = str(s)[:10]
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    return None


def pick(d, *keys, default=None):
    """Primeiro campo presente: tolera variações de nome entre versões da API."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def get_json(url, params=None, headers=None, pausa=0.0, tentativas=5):
    for i in range(tentativas):
        r = _SESSION.get(url, params=params, headers=headers, timeout=60)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(90, 2 ** (i + 1)))
            continue
        if r.status_code in (401, 403):
            raise SystemExit(f"{r.status_code} em {url}: confira a chave PORTAL_API_KEY.")
        r.raise_for_status()
        time.sleep(pausa)
        return r.json()
    raise RuntimeError(f"Falhou após {tentativas} tentativas: {url}")


class Execucao:
    """Registra cada carga em etl_runs (auditoria e base do 'atualizado em')."""
    def __init__(self, con, fonte):
        self.con, self.fonte, self.n = con, fonte, 0

    def __enter__(self):
        cur = self.con.execute("INSERT INTO etl_runs(fonte,inicio,status) VALUES(?,?,'rodando')", (self.fonte, agora()))
        self.id = cur.lastrowid
        return self

    def __exit__(self, tipo, erro, tb):
        self.con.execute("UPDATE etl_runs SET fim=?,registros=?,status=?,erro=? WHERE id=?",
                         (agora(), self.n, "erro" if erro else "ok", str(erro) if erro else None, self.id))
        self.con.commit()
        return False
