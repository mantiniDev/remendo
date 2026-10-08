CREATE TABLE IF NOT EXISTS parlamentares(
  id TEXT PRIMARY KEY,            -- 'C-<id>' (Câmara) ou 'S-<código>' (Senado)
  casa TEXT, nome TEXT, nome_norm TEXT, nome_civil_norm TEXT,
  partido TEXT, uf TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_parl_nome ON parlamentares(nome_norm);
CREATE INDEX IF NOT EXISTS ix_parl_civil ON parlamentares(nome_civil_norm);

CREATE TABLE IF NOT EXISTS emendas(
  codigo TEXT PRIMARY KEY, ano INTEGER, numero TEXT, tipo TEXT,
  autor_nome TEXT, autor_norm TEXT, parlamentar_id TEXT,
  localidade TEXT, funcao TEXT, subfuncao TEXT,
  empenhado INTEGER DEFAULT 0, liquidado INTEGER DEFAULT 0,   -- valores em centavos
  pago INTEGER DEFAULT 0, resto_pago INTEGER DEFAULT 0,
  hash TEXT, raw TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_em_ano ON emendas(ano);
CREATE INDEX IF NOT EXISTS ix_em_parl ON emendas(parlamentar_id);

CREATE TABLE IF NOT EXISTS documentos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  emenda_codigo TEXT, codigo_doc TEXT, data TEXT, fase TEXT, especie TEXT,
  valor INTEGER, raw TEXT,
  UNIQUE(emenda_codigo, codigo_doc, fase)
);
CREATE INDEX IF NOT EXISTS ix_doc_em ON documentos(emenda_codigo);

CREATE TABLE IF NOT EXISTS docs_carregados(   -- emendas cujos documentos já foram baixados (com o hash dos valores na época)
  codigo TEXT PRIMARY KEY, hash TEXT
);

CREATE TABLE IF NOT EXISTS etl_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, fonte TEXT, inicio TEXT, fim TEXT,
  registros INTEGER, status TEXT, erro TEXT
);

DROP VIEW IF EXISTS v_emendas;
CREATE VIEW v_emendas AS
SELECT t.*,
  CASE
    WHEN t.empenhado <= 0 THEN 'sem_empenho'
    WHEN t.pago >= t.empenhado THEN 'paga'
    WHEN t.pago > 0 THEN 'parcial'
    WHEN t.ultima_mov IS NOT NULL AND t.ultima_mov < date('now','-180 days') THEN 'parada'
    ELSE 'empenhada'
  END AS status
FROM (
  SELECT e.*, p.partido, p.uf, p.casa,
    (SELECT MAX(d.data) FROM documentos d WHERE d.emenda_codigo = e.codigo) AS ultima_mov
  FROM emendas e LEFT JOIN parlamentares p ON p.id = e.parlamentar_id
) t;
