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
3. O limite de chamadas por minuto da API é restrito (cerca de 90/min, segundo fonte não oficial). O pipeline espera
   `RATE_PAUSA` segundos entre chamadas (padrão 0,25) e, em erro 429, aguarda 60 s. A primeira carga leva horas:
   com `--max-minutos 300` ela para sozinha, exporta o que já tem e continua de onde parou na execução seguinte
   (os documentos são baixados dos maiores valores para os menores). Enquanto houver emendas sem documentos,
   `meta.json` traz `carga_parcial: true` e `emendas_sem_documentos`.
4. Os nomes exatos dos campos foram lidos da documentação da API e **não foram testados com chave real**.
   Por isso existe o `check_fields`, e o código tolera variações comuns de nome (`pick`).

## Atualização 2 — qualidade dos dados
- `parlamentares.py`: além dos "em exercício", carrega a legislatura 57 (Câmara e Senado), para incluir quem se licenciou ou saiu. Se o endereço da legislatura falhar, a carga segue só com os atuais e avisa no log.
- `emendas.py`: casamento de nomes mais tolerante (prefixos "Dep."/"Sen.", palavras de um nome contidas no outro, só com candidato único); revisão dos autores sem vínculo a cada execução; registro dos códigos repetidos.
- `schema.sql`: coluna `categoria` (individual, bancada, comissão, relator) na view e tabela `emendas_duplicadas`.
- `export.py`: novos `categorias.json`, `nao_vinculados.json`, `duplicados.json`; rankings separados por Casa (`maior_nao_pago_*`, `menos_executam_*`) e `coletivas_menos_executam`; `pct_pago` limitado a 100; `meta.json` com `vinculo_individuais` e `codigos_repetidos`.
- Dado novo: variável opcional `REMENDO_LEGISLATURAS` (padrão `57`).

## Atualização 3
- Código repetido na API = linhas diferentes (ex.: parte "Transferências Especiais" e parte "Finalidade Definida" da mesma emenda). Agora cada linha é guardada (a segunda como `código~2`); cópias exatas são ignoradas. Documentos são baixados só para o código-base.
- Correção do casamento de nomes: pontos e "Dep./Sen." são removidos dos dois lados (antes só do autor, o que desfez o vínculo de "Dr.", "Pr.", "Jr."). Um vínculo existente nunca é apagado se a nova busca falhar.
- Emendas de ex-parlamentar ("NOME (EX-PARLAMENTAR FULANO, NOS TERMOS ...)") passam a usar o nome de FULANO.
- `nao_vinculados.json` agora diz o motivo (`sem_candidato` ou `ambiguo`, com os candidatos).
- Partidos "S.PART." e "S/Partido" viram "Sem partido".
