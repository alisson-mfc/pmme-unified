---
title: PMM-e Dashboard
emoji: 🏥
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
short_description: Dashboard PMM-e — Matrículas + Logbook
---

# PMM-e — Dashboard Unificado

Aplicação Dash consolidando os dois dashboards do **Programa Mais Médicos
Especialistas** (Matrículas + Logbook) num único app, com pipeline automatizado
de anonimização + análise via Claude.

## Estrutura

```
pmme-unified/
├── app.py                       # Entrypoint Dash (tabs Matrículas | Logbook)
├── pages/
│   ├── matriculas.py            # 7 seções + filtro de rede e ano
│   └── logbook.py               # 3 sub-abas (Visão Geral / Diagnóstica / Preditiva)
├── components/                  # theme, header, charts (Plotly factories)
├── data/                        # loader multi-source + parsers + aggregations
├── pipeline/                    # Anonimização + análise Claude + ML (rodado local)
│   ├── anonimizar_matriculas.py
│   ├── anonimizar_logbook.py
│   ├── analise_matriculas.py    # 9 cortes (3 redes × 3 anos) com cache por hash
│   ├── analise_logbook.py       # 3 redes com cache por hash
│   ├── ml_logbook.py            # Random Forest + Gradient Boosting
│   ├── cache.py                 # hash SHA-256 + meta sidecars
│   └── run.py                   # ORQUESTRADOR — entrypoint do pipeline
├── assets/                      # styles.css + nuvens/ (PNGs baixados em runtime)
├── dados/                       # working dir local (gitignored)
│   ├── raw/                     # JSONs brutos que você cola aqui
│   └── processado/              # saída da anonimização
└── analises/                    # saída da análise Claude (gitignored)
```

## Setup local

```powershell
# 1. venv + dependências
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt                         # mínimo para o dashboard
pip install -r requirements-pipeline.txt                # se for rodar o pipeline também

# 2. Variáveis de ambiente
Copy-Item .env.example .env
# Edite .env e preencha:
#   ANTHROPIC_API_KEY=sk-ant-...   (necessário só pra rodar o pipeline)
#   GITHUB_TOKEN=ghp_...           (necessário se o pmme-dados estiver privado)

# 3. Subir o dashboard
python app.py
# Abre em http://localhost:8050
```

O loader tem fallback de fontes (`DATA_SOURCE=auto` por padrão):
1. `dados/processado/` local (saída do pipeline antes do push)
2. `../pmme-dados/` (sibling clonado localmente — útil em dev)
3. GitHub raw via `GITHUB_TOKEN` (produção)

## Pipeline de dados (rodado localmente)

```powershell
# 1. Cole os JSONs brutos em dados/raw/
#    - dados/raw/matriculas_bruto.json
#    - dados/raw/logbook_bruto.json
#
# 2. Rode o pipeline
python -m pipeline.run                # processa só o que mudou (cache por hash)
python -m pipeline.run --dry-run      # mostra o que faria, sem chamar Claude
python -m pipeline.run --force        # ignora cache, refaz tudo
python -m pipeline.run --only matriculas
python -m pipeline.run --no-analyze   # só anonimiza, pula Claude/ML

# 3. Conferir no dashboard (vai mostrar a data nova)
python app.py

# 4. Quando satisfeito, commita e push pra pmme-dados
python -m pipeline.run --push -m "Snapshot maio/2026"
```

O pipeline gera (gitignored):
- `dados/processado/dados_anonimizados.json` + `.meta.json`
- `dados/processado/logbook_pseudonimizados.json` + `.meta.json`
- `dados/processado/logbook_pseudonimizados_mapeamento.csv` (auditoria local)
- `dados/processado/predicoes_ml_dificuldade.json` + `.meta.json`
- `analises/matriculas/{rede}/{ano}/resultados.json` + `nuvens_palavras/*.png`
- `analises/logbook/{rede}/resultados.json`

Com `--push`, esses arquivos são copiados pro `../pmme-dados/` e enviados via
`git pull --rebase` + `git commit` + `git push origin main`.

## Deploy no Render Free

### Opção A: Render Blueprint (mais rápido)

1. Suba o conteúdo de `pmme-unified/` num repo GitHub público (o app não contém dados sensíveis).
2. Acesse [dashboard.render.com/blueprints](https://dashboard.render.com/blueprints) → **New Blueprint Instance**.
3. Conecte seu repo. Render detecta `render.yaml` e cria o web service automaticamente.
4. No serviço criado → **Environment** → adicione `GITHUB_TOKEN` com escopo `repo` (necessário pra ler `pmme-dados` privado).
5. Aguarde o deploy (~3 min). URL final: `https://pmme-unified.onrender.com`.

### Opção B: Manual (sem Blueprint)

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service** → conecta o repo.
2. Configure:
   - **Runtime:** Python 3
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app:server --bind 0.0.0.0:$PORT --workers 1 --timeout 120`
   - **Plan:** Free
3. **Environment Variables:**
   ```
   GITHUB_TOKEN=ghp_...
   GITHUB_REPO=alisson-mfc/pmme-dados
   GITHUB_BRANCH=main
   DATA_SOURCE=remote
   DASH_DEBUG=false
   PYTHON_VERSION=3.11.9
   ```
4. **Create Web Service**. Primeiro build leva ~3-5 min.

### Notas sobre o Free Tier

- **Dorme** após 15 min de inatividade. Primeiro acesso após sleep leva ~30 s pra acordar.
- **512 MB RAM**: usamos `--workers 1` pra caber. Se faltar memória, considere o Starter plan.
- **Disco efêmero**: os PNGs de nuvem baixados ficam em `assets/nuvens/` durante a vida da instância; são re-baixados após restart.

## Quando uma nova base de dados chega

O fluxo completo (assumindo que você tem os JSONs brutos novos):

```powershell
# Substitua os arquivos em dados/raw/ pelos novos
Copy-Item C:\downloads\matriculas_novo.json dados\raw\matriculas_bruto.json
Copy-Item C:\downloads\logbook_novo.json dados\raw\logbook_bruto.json

# Rode o pipeline (chamará Claude apenas pros cortes que mudaram)
python -m pipeline.run --push -m "Atualização <data>"

# Render redeploya automaticamente em ~1-2 min após o push no pmme-dados
# (porque a app lê do GitHub raw — não precisa redeployar o app em si)
```

## Variáveis de ambiente

| Variável | Onde usar | Obrigatória? |
|---|---|---|
| `ANTHROPIC_API_KEY` | pipeline local | Sim — pra análise Claude |
| `GITHUB_TOKEN` | pipeline local + Render | Sim se `pmme-dados` é privado |
| `GITHUB_REPO` | Render | Default: `alisson-mfc/pmme-dados` |
| `GITHUB_BRANCH` | Render | Default: `main` |
| `DATA_SOURCE` | dev opcional, Render obrigatório | `auto` em dev, `remote` em prod |
| `DASH_DEBUG` | Render | `false` em prod |
| `PORT` | Render | Definido automaticamente pelo Render |
| `CLAUDE_MODEL_SENTIMENTO` | pipeline opcional | Default: `claude-sonnet-4-6` |
| `CLAUDE_MODEL_RESUMO` | pipeline opcional | Default: `claude-sonnet-4-6` |
| `CLAUDE_MODEL_TOPICOS` | pipeline opcional | Default: `claude-sonnet-4-6` |

## Migração das análises antigas

Atualmente as análises de matrículas vivem em **`pmme-dashboard/analises/`** (3 redes, sem dimensão de ano). Após a primeira execução do pipeline com `--push`, elas migram pra **`pmme-dados/analises/matriculas/{rede}/{ano}/`** (9 cortes).

O loader tem fallback pra estrutura antiga (apenas quando `ano=Todos`), então o dashboard continua funcionando durante a transição. Quando você terminar a primeira execução do pipeline, pode arquivar/remover `pmme-dashboard/analises/` se quiser.
