# Remendo: contexto do projeto

Site de transparência de emendas parlamentares (https://remendo.com.br). Os dados vêm do Portal da Transparência,
da API da Câmara e do Senado, passam por um ETL diário em Python/SQLite (`remendo_etl/`) e viram um site estático
(`site/`), publicado no GitHub Pages pelo workflow `.github/workflows/atualizar.yml` (todo dia às 07:00 UTC ou manual).
Segredo necessário: `PORTAL_API_KEY`.

## Decisões técnicas

- Valores em centavos. "Pago" = `valorPago + valorRestoPago`; o percentual pago é limitado a 100%.
- View `v_emendas`: `status` (sem_empenho, empenhada, parcial, paga, parada = mais de 180 dias), `categoria`
  (individual, bancada, comissão, relator, outra) e `parlamentar_nome`.
- `codigoEmenda` repetido com conteúdo diferente vira `codigo`, `codigo~2`… (diagnóstico em `emendas_duplicadas`).
- Vínculo autor → parlamentar: `_limpa` nos dois lados (pontos e títulos), nome exato e depois subconjunto de
  palavras (mínimo 2, candidato único), só o texto antes de "("; `COALESCE` preserva vínculos antigos.
- Cerca de 43–48% do valor é de bancada/comissão, sem autor individual. É esperado.
- `REMENDO_LEGISLATURAS` (padrão 57). `docs_carregados` permite retomar o download; `--max-minutos 300`.

## Estado em 28/10/2026

- Workflow rodando todo dia com sucesso (execução 28: ETL em ~31 min, deploy ok).
- Listas 2024–2026 completas; restavam 140 emendas com documentos a baixar.
- Senado: os dois endpoints responderam sem erro em execuções reais. A partir desta versão o log mostra quantos
  senadores vieram de cada endpoint e avisa se vier zero.

## Pendências

- Vínculo das individuais: 98,5–98,9% do valor em 2024–2026. Seis autores (Fabio Garcia, Waldemar Oliveira,
  Rodolfo Nogueira, Eduardo Velloso, Bebeto, Reginete Bispo) ficavam ambíguos com homônimos `S-…` vindos dos
  suplentes da lista da legislatura do Senado; agora suplentes sem exercício são ignorados. Os quatro sem
  candidato (nome diferente na Câmara: Yury do Paredão, Dayany Bittencourt, Rafael Bento, Marcivania Flexa) estão
  em `APELIDOS`, em `remendo_etl/emendas.py`, com ids conferidos no site da Câmara.
- Conferir no navegador se o status "parada" está preenchido e se "Enforce HTTPS" está marcado no Pages.
- Favorecidos: são ~257 mil empenhos (~13 por emenda) a ~110 consultas/min, ~30 mil por execução. A fila consulta
  primeiro um empenho de cada emenda sem favorecido (~1 execução para cobrir quase todas) e depois o resto
  (~6 dias). Acompanhar no log `favorecidos: N/M empenhos` e em `meta.json` (`favorecidos_pendentes`,
  `cobertura_favorecidos`).
- Cota parlamentar: feita (Atualização 6 do README). Fontes conferidas em 30/10/2026: o CSV anual da Câmara traz
  `ideCadastro` (o JSON anual não traz); a API administrativa do Senado traz `codSenador`. Falta o limite mensal
  por UF (não está nas bases). Verba de gabinete, pessoal, imóvel funcional etc.: ainda sem fonte estruturada.
- Cruzamento cota × emendas: feito, na página do parlamentar. Regras combinadas com o autor do projeto:
  - casar só por CNPJ completo e idêntico, nunca por nome; CPF fica de fora (vem mascarado no Portal);
  - cada linha com link para a nota fiscal (Câmara/Senado) e para o empenho (Portal da Transparência);
  - aviso visível na seção, na página e na metodologia: os dados são extraídos automaticamente dos sites do
    governo, coincidência não indica irregularidade e toda informação precisa de verificação confirmada na fonte
    oficial antes de qualquer uso;
  - linguagem neutra ("aparece nas duas bases"), sem rankings de "suspeitos".
- Ideias: valor indicado (SIOP), página por município e por favorecido (CNPJ), imagens de compartilhamento por
  parlamentar, cruzar CNES com o cadastro de estabelecimentos de saúde.
