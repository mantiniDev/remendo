# Remendo — site + publicação automática

## O que há aqui
- `site/` — o site (páginas, estilo, JavaScript, fontes, ícones). Não tem dados: os dados entram na publicação.
- `.github/workflows/atualizar.yml` — coleta os dados, exporta e **publica no GitHub Pages** todo dia (04h de Brasília).
- `remendo_etl/` — arquivos do pipeline que mudaram (exportação com emendas em JSON, UF e datas).

## Colocar no repositório
Extraia o zip na raiz do repositório (mesmos caminhos), depois:
    git add .
    git commit -m "Site do Remendo e publicação no GitHub Pages"
    git push

## Ligar o GitHub Pages (uma vez)
1. No repositório: **Settings → Pages**.
2. Em **Build and deployment → Source**, escolha **GitHub Actions**.
3. Vá em **Actions → Atualizar dados e publicar o site → Run workflow** (deixe "anos" em branco).
4. Ao terminar, o endereço aparece no job "publicar" e em Settings → Pages (algo como `https://mantinidev.github.io/remendo/`).

Observação: pelo endereço `mantinidev.github.io/remendo/` o site funciona, mas só no domínio próprio os links começados com `/` (página 404) ficam certos.

## Ligar o remendo.com.br
1. Em **Settings → Pages → Custom domain**, digite `remendo.com.br` e salve.
2. No painel do seu registro de domínio (Registro.br ou onde estiver o DNS), crie:
   - 4 registros **A** para `remendo.com.br`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - 1 registro **CNAME** para `www`: `mantinidev.github.io`
   (confirme os números na ajuda do GitHub Pages: “Managing a custom domain for your GitHub Pages site”.)
3. Quando o GitHub validar o DNS (pode levar de minutos a horas), marque **Enforce HTTPS**.

## Ver o site no seu computador
O navegador não deixa abrir os dados direto do arquivo. Depois de uma execução do workflow:
baixe o artefato `dados-remendo`, ponha seu conteúdo em `site/dados/` e rode, dentro de `site/`:
    python -m http.server 8000
e abra http://localhost:8000
