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
4. Os nomes dos campos foram conferidos com a chave real nas execuções diárias do workflow. O `check_fields` e a
   tolerância a variações de nome (`pick`) continuam no código para avisar se a API mudar.

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

## Atualização 4: quem recebeu (favorecidos)
- `emendas.py`: depois dos documentos, consulta `/despesas/documentos/{codigo}` para cada **empenho** e grava o favorecido (CNPJ, nome, UF), a modalidade, o órgão e a observação na tabela `favorecidos`. A carga é retomável e usa o tempo que sobra do `--max-minutos`. Liquidação e pagamento ficam de fora, porque neles o favorecido pode ser um intermediário (ex.: Banco do Brasil num pagamento em lote) e o valor é o do lote. Um documento que a API não encontra (400/404) é registrado com `erro` e não é consultado de novo.
- `export.py`: novos `favorecidos.json` (ranking por favorecido e ano, indicações e cobertura) e `favorecidos_{ano}.json` (favorecidos, CNES e indicação de cada emenda, pelo código-base). O CSV ganha `favorecido_cnpj`, `favorecido_nome` e `indicado_por`. O `meta.json` traz `favorecidos_pendentes` e `cobertura_favorecidos`.
  - Quando uma emenda tem mais de um favorecido, empenhado e pago são divididos na proporção dos empenhos (reforços somam, anulações subtraem).
  - CNES e indicação ("DA SENADORA FULANA", "PELO DEPUTADO …") são lidos do texto livre da observação. A indicação só é extraída em emendas de comissão, bancada ou relator.
- Site: seção "Quem recebeu" na página da emenda e nova página `favorecidos.html` ("Quem recebe"), com filtro por natureza (entidade privada, ente ou fundo público, aplicação direta).
- Workflow manual "Conferir campos da API" (`check_fields.yml`): mostra os campos reais dos três endpoints.

## Atualização 5: fila de favorecidos e apelidos
- Fila de favorecidos: são cerca de 257 mil empenhos (uns 13 por emenda), a cerca de 110 consultas por minuto, ou uns 30 mil por execução. A fila consulta primeiro o empenho mais antigo de cada emenda que ainda não tem favorecido. Depois vêm os demais, que refinam a divisão do valor quando a emenda tem mais de um favorecido.
- Apelidos (`APELIDOS` em `remendo_etl/emendas.py`): servem para autores cujo nome no Portal é diferente do nome na Câmara ou no Senado. A chave é o nome normalizado como `candidatos` compara (sem acento, sem pontos e títulos, só o texto antes do "("). O valor é o id do parlamentar. Use só ids conferidos no site da Casa (`camara.leg.br/deputados/<id>`). Se o id não estiver na tabela de parlamentares, a revisão diária avisa no log e não vincula.

  | Autor no Portal | Id | Nome na Câmara |
  |---|---|---|
  | YURY DO PAREDAO | C-220660 | Yury do Paredão |
  | DAYANY BITTENCOURT | C-220659 | Dayany Bittencourt |
  | RAFAEL BENTO | C-233594 | Rafael Fera (assumiu em 2025 no lugar de Lebrão) |
  | MARCIVANIA FLEXA | C-160641 | Professora Marcivânia (assumiu em 2025 no lugar de Maria Goreth) |
