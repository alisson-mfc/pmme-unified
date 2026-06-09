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

# PMM-e — Dashboard de Análise de Dados

Aplicação web para visualização e análise dos dados do **Programa Mais Médicos
Especialistas (PMM-e)** — iniciativa brasileira de formação de médicos
especialistas em regiões prioritárias do Sistema Único de Saúde (SUS), por
meio de cursos de aprimoramento conduzidos em parceria com hospitais de
ensino e instituições formadoras de referência.

## O que o dashboard apresenta

A aplicação consolida duas bases distintas — perfil dos matriculados e
registros clínicos de logbook — em uma interface única dividida em dois
módulos principais.

### 📋 Matrículas

Perfil demográfico, formação acadêmica, especialidades e distribuição
geográfica dos profissionais matriculados, com filtros dinâmicos por **rede
formadora** e por **edital de entrada**.

- **Dados Gerais:** raça, sexo, idade, estado civil, identidade de gênero,
  ações afirmativas, tempo de formação, residências médicas e títulos de
  especialista
- **Geografia:** mapas interativos do Brasil com drilldown estado → município,
  cobrindo nascimento, graduação, registro profissional (CRM) e vaga atual
- **Temas:** apropriação dos profissionais sobre eixos centrais do SUS
  (organização de redes de atenção, coordenação do cuidado, gestão da clínica,
  saúde baseada em evidências, plataformas digitais)
- **Qualitativa:** análises de respostas abertas com nuvens de palavras,
  classificação automática de sentimentos e resumos executivos

### 🩺 Logbook

Registros de procedimentos clínicos realizados pelos aprimorandos durante o
programa, com filtros por rede formadora, período, curso, instituição
formadora e hospital de atuação.

- **Visão Geral:** evolução temporal dos atendimentos, top instituições e
  hospitais, distribuição de níveis de desenvolvimento (escala Ten Cate) e
  dificuldade clínica
- **Geografia:** mapa coroplético dos procedimentos por estado e município
- **Análise Diagnóstica:** progressão dos profissionais ao longo do tempo,
  mapa de calor complexidade × proficiência, análise comparativa entre
  cursos e instituições, perfil de atendimentos de alta complexidade
- **Análise Preditiva:** agrupamento temático de procedimentos descritos em
  campo livre, identificação de perfis de aprendizado dos aprimorandos e
  predição de dificuldade para CIDs e procedimentos

## Uso de Inteligência Artificial

A aplicação utiliza modelos de linguagem (Google Gemini) para análises
textuais que seriam inviáveis manualmente:

- **Análise de sentimentos** em respostas abertas dos profissionais,
  classificadas como positivas, neutras ou negativas
- **Resumos executivos** das respostas qualitativas por rede e edital
- **Agrupamento temático** de procedimentos descritos em texto livre, quando
  não há código padronizado disponível

Adicionalmente, modelos de aprendizado de máquina supervisionado
(Random Forest e Gradient Boosting) são empregados para estimar a dificuldade
de procedimentos com base no diagnóstico (CID), procedimento e contexto
clínico, usando o histórico de registros como base de treinamento.

## Privacidade e dados sensíveis

Todos os dados exibidos são **pseudonimizados ou anonimizados** antes de
qualquer processamento ou armazenamento:

- Nomes, CPFs, números de documentos, e-mails, telefones e endereços são
  removidos ou mascarados
- Identificadores de profissionais são substituídos por tokens irreversíveis
  gerados via hashing criptográfico (SHA-256 com salt)
- A base de dados é armazenada em repositório de acesso restrito e
  autenticado

## Tecnologias

- **Aplicação web:** Dash + Plotly + dash-bootstrap-components
- **Linguagem:** Python 3.11
- **IA generativa:** Google Gemini 3.1 Flash Lite
- **Machine Learning:** scikit-learn (Random Forest, Gradient Boosting)
- **Dados geográficos:** API IBGE de municípios brasileiros, geojsons abertos
- **Containerização e deploy:** Docker em Hugging Face Spaces

## Acesso

A aplicação está disponível em
**[huggingface.co/spaces/alisson-mfc/pmme-unified](https://huggingface.co/spaces/alisson-mfc/pmme-unified)**.

---

## Para desenvolvedores

### Setup local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt                # mínimo para o dashboard
pip install -r requirements-pipeline.txt       # se for rodar o pipeline
python app.py                                  # http://localhost:8050
```

Configurar `.env` com `GEMINI_API_KEY` (pipeline) e `GITHUB_TOKEN` (leitura
do repositório de dados privado).

### Pipeline de dados

O pipeline processa JSONs brutos colocados em `dados/raw/`, gera versões
anonimizadas, executa análises via IA com cache por hash e sincroniza o
resultado com o repositório de dados.

```powershell
python -m pipeline.run                  # processa só o que mudou
python -m pipeline.run --dry-run        # mostra o que faria, sem chamar IA
python -m pipeline.run --force          # ignora cache e refaz tudo
python -m pipeline.run --push           # ao final, commita e empurra os dados
```

Os filtros (rede formadora, edital) são **detectados dinamicamente** a partir
do JSON em tempo de execução — não requerem alteração de código quando novas
redes ou editais aparecem.
