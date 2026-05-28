FROM python:3.11-slim

# Diretório do app
WORKDIR /code

# Dependências de sistema (compilar wheels, fontes pra wordcloud, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python primeiro (build cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . .

# HF Spaces espera o app em /home/user/app (cria usuário não-root)
RUN useradd -m -u 1000 user \
    && chown -R user:user /code

USER user

# Porta padrão do HF Spaces
EXPOSE 7860

# Sobe via gunicorn
CMD ["gunicorn", "app:server", \
     "--bind", "0.0.0.0:7860", \
     "--workers", "1", \
     "--timeout", "180"]
