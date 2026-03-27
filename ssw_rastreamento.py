"""
Sistema de Rastreamento SSW - Versão CLI e Web
Use este mesmo arquivo para ambos: linha de comando e web
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import os
import re
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ============================================
# CONFIGURAÇÕES
# ============================================

# Configuração de logging padrão
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ssw_rastreamento.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Cores para Excel
CORES = {
    'ENTREGUE': 'E3F2E3',
    'ALERTA_3DIAS': 'FFF3CD',
    'ALERTA_2DIAS': 'FFE5B4',
    'ALERTA_1DIA': 'FFD8B1',
    'ATRASADO': 'FFE0E0',
    'DEVOLVIDO': 'FFB6B6',
    'SEM_DADOS': 'F0F0F0',
    'ERRO': 'FFCCCC',
    'PADRAO': 'FFFFFF'
}

class ProcessadorSSW:
    """
    Classe principal para processamento de rastreamento SSW
    """
    
    def __init__(self, delay_consultas: float = 1.5, callback_log=None):
        """
        Inicializa o processador
        
        Args:
            delay_consultas: Tempo entre consultas
            callback_log: Função para logs (opcional, para interface web)
        """
        self.delay = delay_consultas
        self.callback_log = callback_log
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.base_url = "https://ssw.inf.br/app/tracking"
        self.total_consultas = 0
        self.total_erros = 0
        self.total_sem_dados = 0
        
    def _log(self, mensagem: str, nivel: str = "info"):
        """Envia log para callback ou para o logger padrão"""
        if self.callback_log:
            self.callback_log(mensagem, nivel)
        else:
            if nivel == "erro":
                logger.error(mensagem)
            elif nivel == "aviso":
                logger.warning(mensagem)
            else:
                logger.info(mensagem)
    
    # ============================================
    # SEUS MÉTODOS EXISTENTES (copie exatamente como estão)
    # ============================================
    
    def extrair_chave_nfe(self, texto) -> Optional[str]:
        """Extrai a chave de 44 dígitos"""
        if pd.isna(texto) or not texto:
            return None
        
        texto = str(texto).strip()
        
        if 'ssw.inf.br/app/tracking/' in texto:
            chave = texto.split('tracking/')[-1].split('?')[0].split('#')[0]
            if len(chave) >= 44:
                return chave[:44]
        
        chave = re.sub(r'[^0-9]', '', texto)
        if len(chave) == 44:
            return chave
        
        numeros = re.findall(r'\d{44}', texto)
        if numeros:
            return numeros[0]
        
        return None
    
    def ler_planilha(self, caminho_arquivo: str, coluna_xml: str) -> pd.DataFrame:
        """Lê a planilha de entrada"""
        self._log(f"📂 Lendo arquivo: {caminho_arquivo}")
        
        ext = Path(caminho_arquivo).suffix.lower()
        
        try:
            if ext == '.csv':
                df = pd.read_csv(caminho_arquivo, encoding='utf-8-sig')
            elif ext in ['.xlsx', '.xls']:
                df = pd.read_excel(caminho_arquivo)
            else:
                raise ValueError(f"Formato não suportado: {ext}")
            
            if coluna_xml not in df.columns:
                raise ValueError(f"Coluna '{coluna_xml}' não encontrada")
            
            df['chave_nfe'] = df[coluna_xml].apply(self.extrair_chave_nfe)
            
            total = len(df)
            validas = df['chave_nfe'].notna().sum()
            self._log(f"✅ Chaves válidas: {validas}/{total}")
            
            return df.dropna(subset=['chave_nfe'])
            
        except Exception as e:
            self._log(f"❌ Erro: {e}", "erro")
            raise
    
    def verificar_pagina_sem_dados(self, soup: BeautifulSoup) -> bool:
        """Verifica se a página retornou 'Parâmetros insuficientes'"""
        texto_pagina = soup.get_text().upper()
        frases_sem_dados = [
            'PARÂMETROS INSUFICIENTES PARA PESQUISA',
            'PARAMETROS INSUFICIENTES PARA PESQUISA',
            'NENHUM DADO ENCONTRADO',
            'RASTREAMENTO NÃO ENCONTRADO'
        ]
        
        for frase in frases_sem_dados:
            if frase in texto_pagina:
                return True
        
        div_geral = soup.find('div', class_='geral')
        if div_geral:
            tabelas = div_geral.find_all('table')
            if len(tabelas) < 2:
                return True
            if len(tabelas) >= 2:
                linhas = tabelas[1].find_all('tr')
                if len(linhas) <= 1:
                    return True
        
        return False
    
    def extrair_previsao(self, texto: str) -> Optional[str]:
        """Extrai data de previsão de entrega"""
        if not texto:
            return None
        
        padroes = [
            r'Previsao de entrega:?\s*(\d{2}/\d{2}/\d{2})',
            r'Previsão de entrega:?\s*(\d{2}/\d{2}/\d{2})',
            r'previsão:?\s*(\d{2}/\d{2}/\d{2})',
            r'entrega prevista:?\s*(\d{2}/\d{2}/\d{2})'
        ]
        
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def calcular_dias(self, previsao: str) -> Optional[int]:
        """Calcula dias para a previsão"""
        if not previsao:
            return None
        
        try:
            dia, mes, ano = previsao.split('/')
            data_prev = datetime.strptime(f"20{ano}-{mes}-{dia}", "%Y-%m-%d")
            data_prev = data_prev.replace(hour=23, minute=59, second=59)
            
            hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return (data_prev - hoje).days
        except:
            return None
    
    def extrair_dados_pedido(self, soup: BeautifulSoup) -> Dict:
        """Extrai dados do pedido"""
        dados = {
            'nota_fiscal': '',
            'numero_pedido': '',
            'remetente': '',
            'destinatario': ''
        }
        
        try:
            tabelas = soup.find_all('table')
            if not tabelas:
                return dados
            
            linhas = tabelas[0].find_all('tr')
            for linha in linhas:
                texto = linha.get_text(strip=True)
                celulas = linha.find_all('td')
                
                if 'N Fiscal:' in texto and len(celulas) > 3:
                    dados['nota_fiscal'] = celulas[3].get_text(strip=True)
                elif 'N Pedido:' in texto and len(celulas) > 5:
                    dados['numero_pedido'] = celulas[5].get_text(strip=True)
                elif 'Remetente:' in texto and len(celulas) > 1:
                    dados['remetente'] = celulas[1].get_text(strip=True)
                elif 'Destinat' in texto and len(celulas) > 1:
                    dados['destinatario'] = celulas[1].get_text(strip=True)
                    
        except Exception as e:
            pass
        
        return dados
    
    def extrair_historico(self, soup: BeautifulSoup) -> List[Dict]:
        """Extrai histórico de rastreamento"""
        historico = []
        
        try:
            div_geral = soup.find('div', class_='geral')
            if not div_geral:
                return historico
            
            tabelas = div_geral.find_all('table')
            if len(tabelas) < 2:
                return historico
            
            linhas = tabelas[1].find_all('tr')
            
            for linha in linhas:
                celulas = linha.find_all('td')
                if len(celulas) < 3:
                    continue
                
                data_hora = celulas[0].get_text(strip=True).replace('\n', ' ')
                
                if not data_hora or data_hora == 'Data/Hora':
                    continue
                
                local = celulas[1].get_text(strip=True).replace('\n', ' ')
                
                titulo = celulas[2].find('p', class_='titulo')
                if titulo:
                    situacao = titulo.get_text(strip=True)
                    detalhes = celulas[2].get_text(strip=True).replace(situacao, '').strip()
                else:
                    situacao = celulas[2].get_text(strip=True).split('.')[0]
                    detalhes = celulas[2].get_text(strip=True)
                
                historico.append({
                    'data_hora': data_hora,
                    'local': local,
                    'situacao': situacao,
                    'detalhes': detalhes[:300]
                })
                
        except Exception as e:
            pass
        
        return historico
    
    def verificar_entrega(self, historico: List[Dict]) -> Tuple[bool, str, str]:
        """Verifica se foi entregue"""
        for evento in historico:
            if 'ENTREGUE' in evento['situacao'].upper():
                return True, evento['data_hora'], evento['situacao']
        return False, '', ''
    
    def verificar_devolucao(self, historico: List[Dict]) -> bool:
        """Verifica se foi devolvido"""
        for evento in historico:
            situacao = evento['situacao'].upper()
            if any(p in situacao for p in ['DEVOLVIDA', 'DEVOLUÇÃO', 'REMETENTE']):
                return True
        return False
    
    def classificar_status(self, entregue: bool, devolvido: bool, dias: Optional[int], sem_dados: bool = False) -> Dict:
        """Classifica o status com nomes mais claros"""
        
        if sem_dados:
            return {
                'status': 'AGUARDANDO RASTREIO',
                'status_resumo': 'AGUARDANDO',
                'recomendacao': 'Sem Rastreio SSW.',
                'cor': CORES['SEM_DADOS'],
                'prioridade': 4
            }
        
        if devolvido:
            return {
                'status': 'DEVOLVIDO AO REMETENTE',
                'status_resumo': 'DEVOLVIDO',
                'recomendacao': 'Contatar cliente e transportadora para reenvio',
                'cor': CORES['DEVOLVIDO'],
                'prioridade': 1
            }
        
        if entregue:
            return {
                'status': 'ENTREGUE',
                'status_resumo': 'ENTREGUE',
                'recomendacao': 'Atualizar Intelipost e dar baixa no sistema',
                'cor': CORES['ENTREGUE'],
                'prioridade': 5
            }
        
        if dias is None:
            return {
                'status': 'EM TRÂNSITO',
                'status_resumo': 'TRÂNSITO',
                'recomendacao': 'Em trânsito, aguardando atualização de previsão',
                'cor': CORES['PADRAO'],
                'prioridade': 4
            }
        
        # Atrasado - exibe "ATRASADO A (X Dias)"
        if dias < 0:
            dias_atraso = abs(dias)
            return {
                'status': f'ATRASADO A ({dias_atraso} {"dia" if dias_atraso == 1 else "dias"})',
                'status_resumo': f'ATRASADO {dias_atraso}d',
                'recomendacao': f'Cobrar transportadora - Atraso de {dias_atraso} dias',
                'cor': CORES['ATRASADO'],
                'prioridade': 2
            }
        
        # Próximo ao prazo - exibe "PREVISÃO VENCENDO EM (X Dias)"
        if dias <= 3:
            if dias == 1:
                cor = CORES['ALERTA_1DIA']
                recomendacao = 'ALERTA - Previsão para amanhã'
            elif dias == 2:
                cor = CORES['ALERTA_2DIAS']
                recomendacao = 'Atenção - 2 dias para o prazo'
            else:  # 3 dias
                cor = CORES['ALERTA_3DIAS']
                recomendacao = 'Pré-alerta - 3 dias para o prazo'
            
            return {
                'status': f'PREVISÃO VENCENDO EM ({dias} {"dia" if dias == 1 else "dias"})',
                'status_resumo': f'{dias}d',
                'recomendacao': recomendacao,
                'cor': cor,
                'prioridade': 3
            }
        
        # No prazo
        return {
            'status': f'NO PRAZO ({dias} {"dia" if dias == 1 else "dias restantes"})',
            'status_resumo': f'{dias}d',
            'recomendacao': 'Dentro do prazo - Monitorar',
            'cor': CORES['PADRAO'],
            'prioridade': 4
        }
    
    def consultar_pedido(self, chave: str) -> Dict:
        """Consulta um pedido no SSW"""
        url = f"{self.base_url}/{chave}"
        self.total_consultas += 1
        
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            sem_dados = self.verificar_pagina_sem_dados(soup)
            
            if sem_dados:
                self.total_sem_dados += 1
                self._log(f"📭 {chave[:20]}... - AGUARDANDO RASTREIO")
                
                dados = self.extrair_dados_pedido(soup)
                classificacao = self.classificar_status(False, False, None, sem_dados=True)
                
                return {
                    'nota_fiscal': dados['nota_fiscal'],
                    'numero_pedido': dados['numero_pedido'],
                    'chave_nfe': chave,
                    'destinatario': dados['destinatario'],
                    'remetente': dados['remetente'],
                    'status': classificacao['status'],
                    'recomendacao': classificacao['recomendacao'],
                    'prioridade': classificacao['prioridade'],
                    'previsao': '',
                    'data_entrega': '',
                    'ultima_data': '',
                    'ultima_situacao': 'Aguardando primeiro registro de rastreio',
                    'ultimo_local': '',
                    'total_eventos': 0,
                    'data_consulta': datetime.now().strftime('%d/%m/%Y %H:%M')
                }
            
            dados = self.extrair_dados_pedido(soup)
            historico = self.extrair_historico(soup)
            
            entregue, data_entrega, situacao = self.verificar_entrega(historico)
            devolvido = self.verificar_devolucao(historico)
            
            previsao = None
            dias = None
            if historico:
                previsao = self.extrair_previsao(historico[0].get('detalhes', ''))
                dias = self.calcular_dias(previsao)
            
            classificacao = self.classificar_status(entregue, devolvido, dias)
            ultimo = historico[-1] if historico else {}
            
            resultado = {
                'nota_fiscal': dados['nota_fiscal'],
                'numero_pedido': dados['numero_pedido'],
                'chave_nfe': chave,
                'destinatario': dados['destinatario'],
                'remetente': dados['remetente'],
                'status': classificacao['status'],
                'recomendacao': classificacao['recomendacao'],
                'prioridade': classificacao['prioridade'],
                'previsao': previsao if previsao else '',
                'data_entrega': data_entrega if entregue else '',
                'ultima_data': ultimo.get('data_hora', ''),
                'ultima_situacao': ultimo.get('situacao', ''),
                'ultimo_local': ultimo.get('local', ''),
                'total_eventos': len(historico),
                'data_consulta': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
            
            self._log(f"✅ {chave[:20]}... - {classificacao['status_resumo']}")
            return resultado
            
        except Exception as e:
            self.total_erros += 1
            self._log(f"❌ Erro {chave[:20]}...: {str(e)[:50]}", "erro")
            return {
                'nota_fiscal': '',
                'numero_pedido': '',
                'chave_nfe': chave,
                'destinatario': '',
                'remetente': '',
                'status': 'ERRO NA CONSULTA',
                'recomendacao': f'Erro: {str(e)[:100]}. Verificar manualmente.',
                'prioridade': 1,
                'previsao': '',
                'data_entrega': '',
                'ultima_data': '',
                'ultima_situacao': 'Erro ao acessar SSW',
                'ultimo_local': '',
                'total_eventos': 0,
                'data_consulta': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
    
    def processar_lote(self, df: pd.DataFrame, max_consultas: int = None) -> pd.DataFrame:
        """Processa múltiplos pedidos"""
        if max_consultas:
            df = df.head(max_consultas)
        
        resultados = []
        total = len(df)
        
        self._log(f"🚀 Processando {total} pedidos...")
        
        for idx, row in df.iterrows():
            self._log(f"[{idx+1}/{total}] Consultando...")
            resultado = self.consultar_pedido(row['chave_nfe'])
            
            for col in df.columns:
                if col not in ['chave_nfe', resultado]:
                    resultado[col] = row[col]
            
            resultados.append(resultado)
            
            if idx < total - 1:
                time.sleep(self.delay)
        
        return pd.DataFrame(resultados)
    
    def gerar_relatorios(self, df: pd.DataFrame, nome_base: str):
        """Gera relatórios com formatação por cores"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        

        # ============================================
    # DEBUG: Verificar os dados antes de gerar
    # ============================================
        self._log(f"\n🔍 DEBUG - DADOS RECEBIDOS:")
        self._log(f"   Total de linhas: {len(df)}")
        self._log(f"   Colunas: {df.columns.tolist()}")
        self._log(f"   Primeiros status:")
        for i, status in enumerate(df['status'].head(10)):
            self._log(f"      {i+1}: '{status}' (tipo: {type(status).__name__})")
    
    # Verifica se tem status vazio
        vazios = df[df['status'].isna()].shape[0]
        if vazios > 0:
            self._log(f"   ⚠️ Status vazios: {vazios}")

        # Estatísticas
        entregues = df[df['status'].str.contains('ENTREGUE', na=False)].shape[0]
        aguardando = df[df['status'].str.contains('AGUARDANDO RASTREIO', na=False)].shape[0]
        atrasados = df[df['status'].str.contains('ATRASADO', na=False)].shape[0]
        devolvidos = df[df['status'].str.contains('DEVOLVIDO', na=False)].shape[0]
        erros = df[df['status'].str.contains('ERRO', na=False)].shape[0]
        
        self._log(f"\n📊 RESUMO:")
        self._log(f"   ✅ Entregues: {entregues}")
        self._log(f"   📭 Aguardando rastreio: {aguardando}")
        self._log(f"   ⚠️ Atrasados: {atrasados}")
        self._log(f"   🔄 Devolvidos: {devolvidos}")
        self._log(f"   ❌ Erros: {erros}")
        
        # ============================================
        # RELATÓRIO PRINCIPAL COM CORES
        # ============================================
        arquivo = f"{nome_base}_rastreamento_{timestamp}.xlsx"
        
        # Ordem das colunas
        ordem_colunas = [
            'nota_fiscal', 'numero_pedido', 'destinatario',
            'status', 'recomendacao',
            'previsao', 'data_entrega',
            'ultima_data', 'ultima_situacao', 'ultimo_local',
            'total_eventos', 'data_consulta'
        ]
        
        # Adiciona colunas originais
        for col in df.columns:
            if col not in ordem_colunas and col not in ['chave_nfe', 'remetente', 'prioridade']:
                ordem_colunas.append(col)
        
        colunas_existentes = [c for c in ordem_colunas if c in df.columns]
        df_relatorio = df[colunas_existentes].copy()
        
        with pd.ExcelWriter(arquivo, engine='openpyxl') as writer:
            df_relatorio.to_excel(writer, index=False, sheet_name='Rastreamento')
            
            workbook = writer.book
            worksheet = writer.sheets['Rastreamento']
            
            from openpyxl.styles import PatternFill, Font, Alignment
            from openpyxl.utils import get_column_letter
            
            CORES_EXCEL = {
                'ENTREGUE': CORES['ENTREGUE'],
                'AGUARDANDO RASTREIO': CORES['SEM_DADOS'],
                'DEVOLVIDO': CORES['DEVOLVIDO'],
                'ATRASADO': CORES['ATRASADO'],
                'PREVISÃO VENCENDO EM (1 dia)': CORES['ALERTA_1DIA'],
                'PREVISÃO VENCENDO EM (2 dias)': CORES['ALERTA_2DIAS'],
                'PREVISÃO VENCENDO EM (3 dias)': CORES['ALERTA_3DIAS'],
                'ERRO': CORES['ERRO']
            }
            
            # Cabeçalho
            for col in range(1, len(colunas_existentes) + 1):
                cell = worksheet.cell(row=1, column=col)
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='2F5496', end_color='2F5496', fill_type='solid')
                cell.alignment = Alignment(horizontal='center')
            
            # Aplicar cores
            for row in range(2, len(df_relatorio) + 2):
                status = str(df.iloc[row-2].get('status', ''))
                cor_fundo = CORES['PADRAO']
                
                if 'ENTREGUE' in status:
                    cor_fundo = CORES_EXCEL['ENTREGUE']
                elif 'AGUARDANDO RASTREIO' in status:
                    cor_fundo = CORES_EXCEL['AGUARDANDO RASTREIO']
                elif 'DEVOLVIDO' in status:
                    cor_fundo = CORES_EXCEL['DEVOLVIDO']
                elif 'ATRASADO' in status:
                    cor_fundo = CORES_EXCEL['ATRASADO']
                elif 'PREVISÃO VENCENDO EM (1 dia)' in status:
                    cor_fundo = CORES_EXCEL['PREVISÃO VENCENDO EM (1 dia)']
                elif 'PREVISÃO VENCENDO EM (2 dias)' in status:
                    cor_fundo = CORES_EXCEL['PREVISÃO VENCENDO EM (2 dias)']
                elif 'PREVISÃO VENCENDO EM (3 dias)' in status:
                    cor_fundo = CORES_EXCEL['PREVISÃO VENCENDO EM (3 dias)']
                elif 'ERRO' in status:
                    cor_fundo = CORES_EXCEL['ERRO']
                
                if cor_fundo != CORES['PADRAO']:
                    for col in range(1, len(colunas_existentes) + 1):
                        worksheet.cell(row=row, column=col).fill = PatternFill(start_color=cor_fundo, end_color=cor_fundo, fill_type='solid')
            
            # Ajusta largura
            for col in worksheet.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    try:
                        max_len = max(max_len, len(str(cell.value)))
                    except:
                        pass
                worksheet.column_dimensions[col_letter].width = min(max_len + 2, 50)
        
        self._log(f"✅ Relatório com cores: {arquivo}")
        
        # ============================================
        # RELATÓRIO INTELIPOST (apenas entregues) - CORRIGIDO
        # ============================================
        entregues_df = df[df['status'].str.contains('ENTREGUE', na=False)].copy()
        
        if not entregues_df.empty:
            arquivo2 = f"{nome_base}_intelipost_{timestamp}.csv"
            
            # Verifica se tem data_entrega, se não, cria uma coluna vazia
            if 'data_entrega' not in entregues_df.columns:
                entregues_df['data_entrega'] = ''
            
            # Determina a coluna do número do pedido
            if 'numero_pedido' in entregues_df.columns and entregues_df['numero_pedido'].notna().any():
                col_pedido = 'numero_pedido'
            elif 'nota_fiscal' in entregues_df.columns:
                col_pedido = 'nota_fiscal'
            else:
                col_pedido = 'chave_nfe'
            
            # Cria DataFrame para Intelipost
            df_intel = pd.DataFrame({
                'numero_pedido': entregues_df[col_pedido],
                'data_entrega': entregues_df['data_entrega'],
                'status': 'ENTREGUE'
            })
            
            df_intel.to_csv(arquivo2, index=False, encoding='utf-8-sig')
            self._log(f"✅ Intelipost: {arquivo2}")


# ============================================
# FUNÇÃO PRINCIPAL (para linha de comando)
# ============================================

def main():
    """Função principal para executar via linha de comando"""
    
    print("\n" + "="*60)
    print(" SISTEMA DE RASTREAMENTO SSW - Versão 4.2")
    print("="*60 + "\n")
    
    ARQUIVO_ENTRADA = "pedidos_ssw.xlsx"
    COLUNA_XML = "XML"
    MAX_CONSULTAS = None
    DELAY = 1
    
    if not os.path.exists(ARQUIVO_ENTRADA):
        print(f"❌ Arquivo não encontrado: {ARQUIVO_ENTRADA}")
        return
    
    try:
        processador = ProcessadorSSW(delay_consultas=DELAY)
        
        print("📂 PASSO 1: Lendo planilha...")
        df = processador.ler_planilha(ARQUIVO_ENTRADA, COLUNA_XML)
        
        if df.empty:
            print("❌ Nenhuma chave válida encontrada!")
            return
        
        print("\n🔍 PASSO 2: Consultando SSW...")
        resultados = processador.processar_lote(df, MAX_CONSULTAS)
        
        print("\n📊 PASSO 3: Gerando relatórios...")
        nome_base = Path(ARQUIVO_ENTRADA).stem
        processador.gerar_relatorios(resultados, nome_base)
        
        entregues = resultados[resultados['status'].str.contains('ENTREGUE', na=False)].shape[0]
        
        print("\n" + "="*60)
        print("✅ PROCESSO CONCLUÍDO!")
        print("="*60)
        print(f"📦 Total de pedidos: {len(resultados)}")
        print(f"✅ Entregues: {entregues}")
        print(f"❌ Erros: {processador.total_erros}")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")


if __name__ == "__main__":
    main()