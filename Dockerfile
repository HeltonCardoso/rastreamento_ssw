FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema (necessárias para o pandas)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro (melhor para cache)
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar o resto da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p /app/logs /tmp/ssw_cache

# Expor porta (Render usa 10000)
EXPOSE 10000

# Comando para rodar
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]