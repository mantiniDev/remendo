# Remendo – pipeline de dados

Coleta emendas parlamentares e parlamentares de fontes oficiais, guarda tudo em um banco próprio (SQLite) e
gera os arquivos JSON/CSV que alimentam o site. Roda por rotina (uma vez por dia).

```
Portal da Transparência ─┐
API da Câmara ───────────┼─▶ remendo.db (SQLite) ─▶ saida/*.json e *.csv ─▶ site Remendo
Dados Abertos do Senado ─┘
```

## Fontes

| Fonte | Endereço | Uso |
|---|---|---|
| Portal da Transparência (CGU) | `https://api.portaldatransparencia.gov.br/api-de-dados` | `/emendas` e `/emendas/documentos/{codigo}` |
| Câmara dos Deputados | `https://dadosabertos.camara.leg.br/api/v2/deputados` | deputados, partido e UF |
| Senado Federal | `https://legis.senado.leg.br/dadosabertos/senador/lista/atual` | senadores em exercício |

O Portal da Transparência exige uma chave gratuita, enviada no cabeçalho `chave-api-dados`.
Peça a sua no próprio Portal e guarde-a na variável `PORTAL_API_KEY` (nunca no código).

## Primeiros passos

```bash
pip install -r requirements.txt
export PORTAL_API_KEY="sua-chave"
python -m remendo_etl.check_fields 2024     # 1) confira os campos reais da API
python -m remendo_etl.run --anos 2024       # 2) primeira carga de teste (um ano)
python -m remendo_etl.run                   # 3) carga normal: ano atual e os 2 anteriores
```

Resultado: `remendo.db` e a pasta `saida/` com `resumo.json`, `areas.json`, `partidos.json`, `parlamentares.json`,
`rankings.json`, `meta.json` e um `emendas_<ano>.csv` por ano (usados na página Dados abertos).

## Como cada página do site usa os dados

| Página | Arquivo |
|---|---|
| Home (totais do ano) | `resumo.json`, `meta.json` |
| Parlamentares / perfil | `parlamentares.json`, `emendas_<ano>.csv` |
| Rankings | `rankings.json` |
| Por área | `areas.json` |
| Partidos e bancadas | `partidos.json` |
| Dados abertos | `emendas_<ano>.csv` |
| Metodologia ("atualizado em") | `meta.json` |

## Atualização automática

`.github/workflows/atualizar.yml` roda todo dia, usa o segredo `PORTAL_API_KEY` do repositório e publica `saida/`
como artefato. O banco é guardado em cache entre as execuções, então só as emendas novas ou alteradas
têm os documentos rebaixados. Para outro servidor, basta um `cron` chamando `python -m remendo_etl.run`.

## Regras de negócio (documente na página Metodologia)

- **Valores** ficam em centavos no banco e em reais nos arquivos exportados.
- **% executado** = pago ÷ empenhado.
- **Status**: `sem_empenho`, `empenhada`, `parcial`, `paga` e `parada`. Parada = empenhada, nada paga e sem
  nenhum documento novo há mais de 180 dias (ajuste em `schema.sql`, view `v_emendas`).
- **Vínculo emenda → parlamentar** é feito pelo nome do autor, normalizado (sem acento, maiúsculas). Nome
  ambíguo ou ausente fica sem vínculo em vez de ser atribuído errado. Emendas de bancada e de comissão não
  têm autor individual, então ficam sem parlamentar.
- Cada registro guarda o JSON original (`raw`), para auditoria e correções.

## Limites conhecidos

1. **Valor "indicado" ainda não existe aqui.** O endpoint de emendas do Portal traz empenhado, liquidado e pago, e
   não a dotação proposta. Enquanto o SIOP não for integrado, o site deve falar em "empenhado", não em "prometeu".
2. Só parlamentares **em exercício** são carregados; quem já saiu aparece sem partido e UF.
3. O limite de chamadas por minuto da API é restrito. O pipeline espera `RATE_PAUSA` segundos (padrão 0,7)
   e tenta de novo em erro 429. A primeira carga de vários anos pode levar horas; as seguintes são incrementais.
4. Os nomes exatos dos campos foram lidos da documentação da API e **não foram testados com chave real**.
   Por isso existe o `check_fields`, e o código tolera variações comuns de nome (`pick`).
