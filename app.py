from flask import Flask, render_template, jsonify, send_file, Response, request
from flask_cors import CORS
import pandas as pd
import threading
import time
from datetime import datetime
import io
import base64
import json
import queue
import os
import tempfile
import re
import traceback

from ssw_rastreamento import ProcessadorSSW, logger
from config import *

app = Flask(__name__)
CORS(app)

# ============================================
# GOOGLE SHEETS FIXO (já configurado)
# ============================================

# Verifica se Google Sheets está configurado
GOOGLE_CONFIGURADO = False
try:
    if GOOGLE_SHEETS_URL and os.path.exists(GOOGLE_CREDENTIALS_PATH):
        GOOGLE_CONFIGURADO = True
        print(f"✅ Google Sheets configurado: {GOOGLE_SHEETS_URL}")
    else:
        if not GOOGLE_SHEETS_URL:
            print("⚠️ GOOGLE_SHEETS_URL não configurado")
        if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
            print(f"⚠️ Arquivo de credenciais não encontrado: {GOOGLE_CREDENTIALS_PATH}")
except Exception as e:
    print(f"⚠️ Erro ao verificar Google Sheets: {e}")

def ler_google_sheets():
    """Lê dados do Google Sheets usando configuração fixa"""
    if not GOOGLE_CONFIGURADO:
        raise Exception("Google Sheets não configurado. Verifique config.py")
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        print(f"🔑 Conectando com credenciais: {GOOGLE_CREDENTIALS_PATH}")
        
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Extrai ID da planilha
        if 'spreadsheets/d/' in GOOGLE_SHEETS_URL:
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', GOOGLE_SHEETS_URL)
            if match:
                spreadsheet_id = match.group(1)
            else:
                spreadsheet_id = GOOGLE_SHEETS_URL
        else:
            spreadsheet_id = GOOGLE_SHEETS_URL
        
        print(f"📊 Abrindo planilha ID: {spreadsheet_id}")
        planilha = client.open_by_key(spreadsheet_id)
        
        # Encontra aba que CONTÉM "SSW" no nome (dinâmico)
        worksheets = planilha.worksheets()
        print(f"📑 Abas encontradas: {[ws.title for ws in worksheets]}")
        
        aba = None
        for ws in worksheets:
            if 'SSW' in ws.title.upper():  # Procura por "SSW" em qualquer lugar
                aba = ws.title
                print(f"✅ Aba encontrada: '{aba}' (contém SSW)")
                break
        
        # Se não encontrou nenhuma com SSW, usa a primeira aba
        if not aba and worksheets:
            aba = worksheets[0].title
            print(f"⚠️ Nenhuma aba com 'SSW' encontrada. Usando primeira: {aba}")
        
        if not aba:
            raise Exception("Nenhuma aba encontrada")
        
        worksheet = planilha.worksheet(aba)
        dados = worksheet.get_all_values()
        
        if len(dados) < 2:
            raise Exception("Planilha vazia")
        
        headers = dados[0]
        rows = dados[1:]
        df = pd.DataFrame(rows, columns=headers)
        
        print(f"📋 Colunas encontradas: {df.columns.tolist()}")
        
        # Busca coluna de XML
        coluna_xml = None
        for col in df.columns:
            if 'xml' in col.lower() or 'chave' in col.lower() or 'nfe' in col.lower():
                coluna_xml = col
                break
        
        if not coluna_xml:
            coluna_xml = COLUNA_XML_PADRAO
            print(f"⚠️ Usando coluna padrão: {coluna_xml}")
        
        # Filtra linhas com dados
        df = df[df[coluna_xml].notna()]
        df = df[df[coluna_xml].astype(str).str.strip() != '']
        df = df.rename(columns={coluna_xml: 'chave_nfe'})
        
        print(f"✅ {len(df)} pedidos carregados da aba '{aba}'")
        return df
        
    except ImportError as e:
        logger.error(f"Erro de importação: {e}")
        raise Exception(f"Bibliotecas não instaladas. Execute: pip install gspread google-auth")
    except FileNotFoundError as e:
        logger.error(f"Arquivo de credenciais não encontrado: {e}")
        raise Exception(f"Arquivo de credenciais não encontrado: {GOOGLE_CREDENTIALS_PATH}")
    except Exception as e:
        logger.error(f"Erro Google Sheets: {e}")
        logger.error(traceback.format_exc())
        raise

# ============================================
# PROCESSAMENTO
# ============================================

processos = {}
contador = 0

class Processo:
    def __init__(self, pid):
        self.id = pid
        self.status = "iniciando"
        self.progresso = 0
        self.total = 0
        self.mensagem = ""
        self.stats = {'entregues':0, 'pendentes':0, 'alertas':0, 'atrasados':0, 'devolvidos':0, 'erros':0}
        self.ultimos = []
        self.resultados = None
        self.fila = queue.Queue()
        self.inicio = datetime.now()
        self.fim = None
    
    def to_dict(self):
        return {
            'id': self.id, 'status': self.status,
            'progresso': self.progresso, 'total': self.total,
            'percentual': int((self.progresso / self.total * 100) if self.total > 0 else 0),
            'mensagem': self.mensagem, 'stats': self.stats,
            'ultimos': self.ultimos[-10:],
            'inicio': self.inicio.strftime('%d/%m/%Y %H:%M:%S'),
            'fim': self.fim.strftime('%d/%m/%Y %H:%M:%S') if self.fim else ''
        }
    
    def enviar(self, tipo, dados):
        self.fila.put({'tipo': tipo, 'dados': dados})
    
    def eventos(self):
        while True:
            try:
                yield f"data: {json.dumps(self.fila.get(timeout=30))}\n\n"
            except:
                yield f"data: {json.dumps({'tipo': 'ping'})}\n\n"

def executar(pid, df, coluna_xml, delay):
    p = processos[pid]
    p.status = "processando"
    p.total = len(df)
    p.enviar('inicio', {'total': p.total})
    
    processador = ProcessadorSSW(delay_consultas=delay)
    resultados = []
    
    for idx, row in df.iterrows():
        if p.status == "cancelado":
            break
        
        p.progresso = idx + 1
        p.mensagem = f"Processando {idx+1}/{p.total}"
        
        res = processador.consultar_pedido(row['chave_nfe'])
        for col in df.columns:
            if col not in ['chave_nfe', res]:
                res[col] = row[col]
        resultados.append(res)
        
        status = res.get('status', '')
        if 'ENTREGUE' in status:
            p.stats['entregues'] += 1
        elif 'ATRASADO' in status:
            p.stats['atrasados'] += 1
        elif 'PREVISÃO' in status:
            p.stats['alertas'] += 1
        elif 'DEVOLVIDO' in status:
            p.stats['devolvidos'] += 1
        elif 'ERRO' in status:
            p.stats['erros'] += 1
        else:
            p.stats['pendentes'] += 1
        
        p.ultimos.append({
            'data_hora': datetime.now().strftime('%H:%M:%S'),
            'nota_fiscal': res.get('nota_fiscal', ''),
            'destinatario': res.get('destinatario', '')[:30],
            'status': status
        })
        if len(p.ultimos) > 20:
            p.ultimos.pop(0)
        
        p.enviar('atualizacao', {'progresso': p.progresso, 'total': p.total, 'stats': p.stats, 'ultimo': p.ultimos[-1]})
        
        if idx < p.total - 1:
            time.sleep(delay)
    
    df_res = pd.DataFrame(resultados)
    output = io.BytesIO()
    df_res.to_excel(output, index=False)
    output.seek(0)
    
    p.resultados = {'excel': base64.b64encode(output.getvalue()).decode('utf-8'), 'stats': p.stats}
    p.status = "concluido"
    p.fim = datetime.now()
    p.enviar('concluido', {'stats': p.stats})

# ============================================
# ROTAS
# ============================================

@app.route('/')
def index():
    return render_template('index.html', google_sheets_url=GOOGLE_SHEETS_URL if GOOGLE_CONFIGURADO else "Não configurado")

@app.route('/api/processar', methods=['POST'])
def processar():
    global contador
    fonte = request.form.get('fonte', 'arquivo')
    coluna_xml = request.form.get('coluna_xml', COLUNA_XML_PADRAO)
    delay = float(request.form.get('delay', DELAY_PADRAO))
    
    try:
        print(f"📥 Processando fonte: {fonte}")
        
        if fonte == 'arquivo':
            if 'arquivo' not in request.files:
                return jsonify({'erro': 'Nenhum arquivo'}), 400
            arquivo = request.files['arquivo']
            if arquivo.filename == '':
                return jsonify({'erro': 'Arquivo vazio'}), 400
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(arquivo.read())
                tmp_path = tmp.name
            
            processador_temp = ProcessadorSSW()
            df = processador_temp.ler_planilha(tmp_path, coluna_xml)
            os.unlink(tmp_path)
            print(f"✅ {len(df)} pedidos do arquivo local")
        else:
            if not GOOGLE_CONFIGURADO:
                return jsonify({'erro': 'Google Sheets não configurado. Verifique config.py'}), 400
            df = ler_google_sheets()
            print(f"✅ {len(df)} pedidos do Google Sheets")
        
        if df.empty:
            return jsonify({'erro': 'Nenhuma chave válida encontrada!'}), 400
        
        contador += 1
        pid = f"proc_{contador}_{int(time.time())}"
        p = Processo(pid)
        processos[pid] = p
        
        thread = threading.Thread(target=executar, args=(pid, df, coluna_xml, delay))
        thread.daemon = True
        thread.start()
        
        return jsonify({'process_id': pid})
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/stream/<pid>')
def stream(pid):
    if pid not in processos:
        return Response("", status=404)
    return Response(processos[pid].eventos(), mimetype="text/event-stream", headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    })

@app.route('/api/status/<pid>')
def status(pid):
    if pid not in processos:
        return jsonify({'erro': 'Não encontrado'}), 404
    return jsonify(processos[pid].to_dict())

@app.route('/api/resultado/<pid>')
def resultado(pid):
    if pid not in processos:
        return jsonify({'erro': 'Não encontrado'}), 404
    p = processos[pid]
    if p.status != 'concluido':
        return jsonify({'erro': 'Não concluído'}), 400
    return jsonify(p.resultados)

@app.route('/api/download/<pid>/excel')
def download(pid):
    if pid not in processos:
        return jsonify({'erro': 'Não encontrado'}), 404
    p = processos[pid]
    if p.status != 'concluido':
        return jsonify({'erro': 'Não concluído'}), 400
    data = base64.b64decode(p.resultados['excel'])
    return send_file(
        io.BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'rastreamento_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    )

@app.route('/api/cancelar/<pid>', methods=['POST'])
def cancelar(pid):
    if pid in processos:
        processos[pid].status = "cancelado"
        processos[pid].enviar('cancelado', {})
    return jsonify({'ok': True})

@app.route('/api/limpar/<pid>', methods=['DELETE'])
def limpar(pid):
    if pid in processos:
        del processos[pid]
    return jsonify({'ok': True})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 SSW RASTREAMENTO")
    print("="*60)
    print(f"📁 Arquivo Local: ✅ disponível")
    print(f"🌐 Google Sheets: {'✅ configurado' if GOOGLE_CONFIGURADO else '❌ não configurado'}")
    if GOOGLE_CONFIGURADO:
        print(f"   📊 Planilha: {GOOGLE_SHEETS_URL}")
        print(f"   🔑 Credenciais: {GOOGLE_CREDENTIALS_PATH}")
        print(f"   🔍 Busca aba que contém 'SSW' no nome")
    print("="*60)
    print("🌐 Acesse: http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)