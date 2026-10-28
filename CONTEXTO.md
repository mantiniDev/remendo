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
  suplentes da lista da legislatura do Senado; agora suplentes sem exercício são ignorados. Sem candidato
  (nome diferente na Câmara): Yury do Paredão, Dayany Bittencourt, Rafael Bento, Marcivania Flexa. Para esses,
  preencher `APELIDOS` em `remendo_etl/emendas.py` com ids conferidos.
- Conferir no navegador se o status "parada" está preenchido e se "Enforce HTTPS" está marcado no Pages.
- Ideias: valor indicado (SIOP), página por município, imagens de compartilhamento por parlamentar.
