FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar numpy primeiro (versão específica)
RUN pip install --no-cache-dir numpy==1.24.3

# Copiar e instalar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --no-deps -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt

# Copiar o resto da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p /app/logs /tmp/ssw_cache

EXPOSE 10000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]