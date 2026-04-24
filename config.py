# config.py
import os
import json
import tempfile
from pathlib import Path

# ============================================
# CONFIGURAÇÃO DO GOOGLE SHEETS
# ============================================

# Tenta carregar da variável de ambiente (Render) ou usa o valor fixo (Local)
GOOGLE_SHEETS_URL = os.environ.get('GOOGLE_SHEETS_URL', "https://docs.google.com/spreadsheets/d/1iGDTGSuMB5TuK08x9OHj8JrFhOlcf9XPbWxsmNSUATQ/edit?usp=sharing")

# ============================================
# CREDENCIAIS DO GOOGLE (FUNCIONA LOCAL E REMOTO)
# ============================================

# Opção 1: Variável de ambiente (Render) - MAIS SEGURO
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON', '')

# Opção 2: Arquivo local (desenvolvimento)
LOCAL_CREDENTIALS_PATH = Path(__file__).parent / "credenciais.json"

# Decide qual credencial usar
if GOOGLE_CREDENTIALS_JSON:
    # Modo REMOTO (Render) - cria arquivo temporário com as credenciais
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(GOOGLE_CREDENTIALS_JSON)
            GOOGLE_CREDENTIALS_PATH = f.name
        print("✅ Usando credenciais do ambiente (Render)")
    except Exception as e:
        print(f"⚠️ Erro ao criar credencial temporária: {e}")
        GOOGLE_CREDENTIALS_PATH = None
        
elif LOCAL_CREDENTIALS_PATH.exists():
    # Modo LOCAL - usa arquivo credenciais.json
    GOOGLE_CREDENTIALS_PATH = str(LOCAL_CREDENTIALS_PATH)
    print(f"✅ Usando credenciais locais: {LOCAL_CREDENTIALS_PATH}")
    
else:
    # Nenhuma credencial encontrada
    GOOGLE_CREDENTIALS_PATH = None
    print("⚠️ NENHUMA CREDENCIAL ENCONTRADA!")
    print("   📁 Local: coloque o arquivo 'credenciais.json' na raiz do projeto")
    print("   ☁️ Remoto: configure a variável GOOGLE_CREDENTIALS_JSON no Render")

# ============================================
# TERMO PARA ENCONTRAR A ABA
# ============================================
TERMO_ABA = "SSW"  # Termo para encontrar a aba

# ============================================
# CONFIGURAÇÕES PADRÃO
# ============================================
COLUNA_XML_PADRAO = "CHAVE NFE"
DELAY_PADRAO = 0.5

# ============================================
# WORKERS (threads simultâneas)
# ============================================
WORKERS_PADRAO = int(os.environ.get('SSW_WORKERS', 5))

# ============================================
# VERIFICAÇÃO DE CONFIGURAÇÃO
# ============================================

def is_configured():
    """Verifica se o Google Sheets está configurado corretamente"""
    return bool(GOOGLE_SHEETS_URL and GOOGLE_CREDENTIALS_PATH)

def get_config_status():
    """Retorna status das configurações para debug"""
    return {
        'google_sheets_url': GOOGLE_SHEETS_URL if GOOGLE_SHEETS_URL else '❌ Não configurado',
        'google_credentials': '✅ Configurado' if GOOGLE_CREDENTIALS_PATH else '❌ Não configurado',
        'credencial_origem': 'Render (variável)' if GOOGLE_CREDENTIALS_JSON else 'Local (arquivo)' if LOCAL_CREDENTIALS_PATH.exists() else 'Não encontrado',
        'workers': WORKERS_PADRAO,
        'coluna_xml': COLUNA_XML_PADRAO,
        'termo_aba': TERMO_ABA
    }

# Debug se executar diretamente
if __name__ == "__main__":
    print("\n" + "="*60)
    print("📋 CONFIGURAÇÕES DO SISTEMA SSW")
    print("="*60)
    for key, value in get_config_status().items():
        print(f"   {key}: {value}")
    print("="*60)
    
    if not is_configured():
        print("\n⚠️ ATENÇÃO: Google Sheets NÃO está configurado!")
        print("   Para configurar:")
        print("   1. LOCAL: Coloque o arquivo 'credenciais.json' na raiz")
        print("   2. RENDER: Adicione a variável GOOGLE_CREDENTIALS_JSON")
