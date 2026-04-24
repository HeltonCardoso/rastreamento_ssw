// ============================================
// SSW DASHBOARD - SCRIPT PRINCIPAL (Google Sheets)
// ============================================

let eventSource = null;
let currentProcessId = null;
let statusChart = null;
let startTime = null;

// ============================================
// INICIALIZAÇÃO
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    inicializarGrafico();
    carregarConfiguracoes();
    mostrarNotificacao('✅ Sistema pronto! Clique no botão para iniciar o processamento.', 'success');
});

function inicializarGrafico() {
    const ctx = document.getElementById('statusChart').getContext('2d');
    statusChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Entregues', 'Em Trânsito', 'Atrasados', 'Devolvidos', 'Alertas'],
            datasets: [{
                label: 'Quantidade',
                data: [0, 0, 0, 0, 0],
                backgroundColor: ['#11998e', '#667eea', '#f5576c', '#ff6b6b', '#ff9800'],
                borderRadius: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { position: 'bottom' } },
            scales: {
                y: { beginAtZero: true, ticks: { stepSize: 1 } }
            }
        }
    });
}

function carregarConfiguracoes() {
    const workers = localStorage.getItem('ssw_workers');
    const coluna = localStorage.getItem('ssw_coluna');
    if (workers) document.getElementById('workers').value = workers;
    if (coluna) document.getElementById('coluna_xml').value = coluna;
}

function salvarConfiguracoes() {
    localStorage.setItem('ssw_workers', document.getElementById('workers').value);
    localStorage.setItem('ssw_coluna', document.getElementById('coluna_xml').value);
}

// ============================================
// PROCESSAMENTO (Google Sheets)
// ============================================

async function iniciarProcessamento() {
    salvarConfiguracoes();
    
    const formData = new FormData();
    formData.append('fonte', 'google');  // FORÇA USAR GOOGLE SHEETS
    formData.append('coluna_xml', document.getElementById('coluna_xml').value);
    formData.append('workers', document.getElementById('workers').value);
    formData.append('delay', '1');
    
    // Desabilita botão iniciar
    const btnIniciar = document.getElementById('btn-iniciar');
    btnIniciar.disabled = true;
    btnIniciar.style.opacity = '0.5';
    btnIniciar.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    
    try {
        mostrarNotificacao('🚀 Buscando dados do Google Sheets...', 'info');
        
        const response = await fetch('/api/processar', { 
            method: 'POST', 
            body: formData 
        });
        
        const data = await response.json();
        
        if (data.erro) {
            throw new Error(data.erro);
        }
        
        currentProcessId = data.process_id;
        startTime = Date.now();
        
        // Conecta ao stream
        conectarStream(currentProcessId);
        
        // Mostra seção de progresso
        document.getElementById('progress-section').style.display = 'block';
        
        // Troca botões
        btnIniciar.style.display = 'none';
        document.getElementById('btn-cancelar').style.display = 'flex';
        
        mostrarNotificacao('✅ Processamento iniciado! Acompanhe o progresso.', 'success');
        
    } catch (error) {
        mostrarNotificacao('❌ Erro: ' + error.message, 'error');
        btnIniciar.disabled = false;
        btnIniciar.style.opacity = '1';
        btnIniciar.innerHTML = '<i class="fas fa-play"></i>';
    }
}

function conectarStream(processId) {
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource(`/api/stream/${processId}`);
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        switch(data.tipo) {
            case 'inicio':
                atualizarProgresso(0, data.total);
                mostrarNotificacao(`📊 Encontrados ${data.total} pedidos para processar`, 'info');
                break;
                
            case 'atualizacao':
                atualizarDashboard(data.dados);
                atualizarProgresso(data.dados.progresso, data.dados.total);
                adicionarUltimoProcessado(data.dados.ultimo);
                break;
                
            case 'concluido':
                finalizarProcessamento();
                break;
                
            case 'cancelado':
                resetarInterface();
                mostrarNotificacao('⚠️ Processamento cancelado!', 'warning');
                break;
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('Erro no stream:', error);
        if (eventSource.readyState === EventSource.CLOSED) {
            console.log('Conexão fechada');
        }
    };
}

function atualizarDashboard(dados) {
    const stats = dados.stats;
    
    // Atualiza métricas
    document.getElementById('metric-entregues').textContent = stats.entregues || 0;
    document.getElementById('metric-transito').textContent = stats.pendentes || 0;
    document.getElementById('metric-alerta').textContent = stats.alertas || 0;
    document.getElementById('metric-atrasados').textContent = stats.atrasados || 0;
    document.getElementById('metric-devolvidos').textContent = stats.devolvidos || 0;
    document.getElementById('metric-erros').textContent = stats.erros || 0;
    
    // Atualiza gráfico
    if (statusChart) {
        statusChart.data.datasets[0].data = [
            stats.entregues || 0,
            stats.pendentes || 0,
            stats.atrasados || 0,
            stats.devolvidos || 0,
            stats.alertas || 0
        ];
        statusChart.update();
    }
    
    // Adiciona alerta se necessário
    if (dados.ultimo && (dados.ultimo.status.includes('ATRASADO') || dados.ultimo.status.includes('PREVISÃO'))) {
        adicionarAlerta(dados.ultimo);
    }
}

function adicionarAlerta(alerta) {
    const tbody = document.getElementById('alertas-body');
    
    if (tbody.children.length === 1 && tbody.children[0].innerHTML.includes('Nenhum alerta')) {
        tbody.innerHTML = '';
    }
    
    const diasMatch = alerta.status.match(/(\d+)\s*dias?/);
    const dias = diasMatch ? diasMatch[1] : '-';
    
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${alerta.nota_fiscal || '-'}</td>
        <td><span class="status-badge status-${getStatusClass(alerta.status)}">${alerta.status}</span></td>
        <td>${alerta.previsao || '-'}</td>
        <td>${dias}</td>
    `;
    
    tbody.insertBefore(tr, tbody.firstChild);
    
    while (tbody.children.length > 10) {
        tbody.removeChild(tbody.lastChild);
    }
}

function atualizarProgresso(atual, total) {
    const percentual = total > 0 ? (atual / total * 100) : 0;
    const progressBar = document.getElementById('progress-bar');
    
    progressBar.style.width = `${percentual}%`;
    progressBar.textContent = `${Math.round(percentual)}%`;
    
    document.getElementById('progress-current').textContent = `${atual} de ${total}`;
    document.getElementById('progress-total').textContent = `Total: ${total}`;
    
    if (startTime && atual > 0) {
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = (atual / elapsed).toFixed(1);
        document.getElementById('progress-speed').textContent = `${speed} req/s`;
    }
}

function adicionarUltimoProcessado(ultimo) {
    const tbody = document.getElementById('ultimos-body');
    
    if (tbody.children.length === 1 && tbody.children[0].innerHTML.includes('Aguardando')) {
        tbody.innerHTML = '';
    }
    
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>${ultimo.data_hora || '-'}</td>
        <td>${ultimo.nota_fiscal || '-'}</td>
        <td>${(ultimo.destinatario || '-').substring(0, 25)}</td>
        <td><span class="status-badge status-${getStatusClass(ultimo.status)}">${ultimo.status}</span></td>
    `;
    
    tbody.insertBefore(tr, tbody.firstChild);
    
    while (tbody.children.length > 10) {
        tbody.removeChild(tbody.lastChild);
    }
}

function getStatusClass(status) {
    if (status.includes('ENTREGUE')) return 'entregue';
    if (status.includes('ATRASADO')) return 'atrasado';
    if (status.includes('DEVOLVIDO')) return 'devolvido';
    if (status.includes('PREVISÃO')) return 'alerta';
    if (status.includes('ERRO')) return 'erro';
    return 'transito';
}

function finalizarProcessamento() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    // NÃO limpar o currentProcessId aqui!
    // Mantenha o ID para o download
    
    // Mostra botão de download
    document.getElementById('btn-download').style.display = 'flex';
    document.getElementById('btn-cancelar').style.display = 'none';
    
    // Restaura botão iniciar
    const btnIniciar = document.getElementById('btn-iniciar');
    btnIniciar.style.display = 'flex';
    btnIniciar.disabled = false;
    btnIniciar.style.opacity = '1';
    btnIniciar.innerHTML = '<i class="fas fa-play"></i>';
    
    mostrarNotificacao('✅ Processamento concluído! Clique no botão verde para baixar o relatório.', 'success');
}

async function baixarRelatorio() {
    if (!currentProcessId) {
        mostrarNotificacao('❌ Nenhum processo encontrado para download', 'error');
        return;
    }
    
    try {
        mostrarNotificacao('📥 Gerando relatório Excel...', 'info');
        
        // Abre em nova aba para evitar problemas de CORS
        window.open(`/api/download/${currentProcessId}/excel`, '_blank');
        
        // Versão alternativa via fetch (fallback)
        // const response = await fetch(`/api/download/${currentProcessId}/excel`);
        // if (response.ok) {
        //     const blob = await response.blob();
        //     const url = window.URL.createObjectURL(blob);
        //     const a = document.createElement('a');
        //     a.href = url;
        //     a.download = `rastreamento_${new Date().toISOString().slice(0,19)}.xlsx`;
        //     document.body.appendChild(a);
        //     a.click();
        //     window.URL.revokeObjectURL(url);
        //     a.remove();
        // }
        
        mostrarNotificacao('✅ Download do relatório iniciado!', 'success');
    } catch (error) {
        console.error('Erro no download:', error);
        mostrarNotificacao('❌ Erro ao baixar relatório: ' + error.message, 'error');
    }
}

async function cancelarProcessamento() {
    mostrarModal('Tem certeza que deseja cancelar o processamento?', async () => {
        if (!currentProcessId) return;
        
        try {
            await fetch(`/api/cancelar/${currentProcessId}`, { method: 'POST' });
            resetarInterface();
            mostrarNotificacao('⚠️ Processamento cancelado!', 'warning');
        } catch (error) {
            mostrarNotificacao('❌ Erro ao cancelar', 'error');
        }
    });
}

function resetarInterface() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    currentProcessId = null;
    startTime = null;
    
    document.getElementById('progress-section').style.display = 'none';
    document.getElementById('btn-download').style.display = 'none';
    document.getElementById('btn-cancelar').style.display = 'none';
    
    const btnIniciar = document.getElementById('btn-iniciar');
    btnIniciar.style.display = 'flex';
    btnIniciar.disabled = false;
    btnIniciar.style.opacity = '1';
    btnIniciar.innerHTML = '<i class="fas fa-play"></i>';
}

function carregarDadosHistorico() {
    // Função para recarregar dados históricos se necessário
    mostrarNotificacao('🔄 Atualizando dashboard...', 'info');
}

// ============================================
// MODAL E NOTIFICAÇÕES
// ============================================

function mostrarModal(mensagem, onConfirm) {
    const modal = document.getElementById('modal');
    const modalMessage = document.getElementById('modal-message');
    const confirmBtn = document.getElementById('modal-confirm');
    
    modalMessage.textContent = mensagem;
    modal.style.display = 'flex';
    
    const handler = () => {
        onConfirm();
        fecharModal();
        confirmBtn.removeEventListener('click', handler);
    };
    
    confirmBtn.addEventListener('click', handler);
}

function fecharModal() {
    document.getElementById('modal').style.display = 'none';
}

function mostrarNotificacao(mensagem, tipo) {
    const notif = document.createElement('div');
    notif.className = 'notification';
    
    const cores = {
        success: '#11998e',
        error: '#dc3545',
        warning: '#ff9800',
        info: '#667eea'
    };
    
    notif.innerHTML = `
        <div style="background: white; padding: 12px 20px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.2); border-left: 4px solid ${cores[tipo] || '#667eea'};">
            ${mensagem}
        </div>
    `;
    
    document.body.appendChild(notif);
    setTimeout(() => notif.remove(), 4000);
}