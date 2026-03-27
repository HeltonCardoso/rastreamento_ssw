let processId = null;
let eventSource = null;

function toggleFonte() {
    const fonte = document.querySelector('input[name="fonte"]:checked').value;
    const campoArquivo = document.getElementById('campo-arquivo');
    const campoGoogle = document.getElementById('campo-google');
    
    if (fonte === 'arquivo') {
        campoArquivo.classList.remove('hidden');
        campoGoogle.classList.add('hidden');
    } else {
        campoArquivo.classList.add('hidden');
        campoGoogle.classList.remove('hidden');
    }
}

function atualizarDashboard(stats) {
    document.getElementById('stat-entregues').textContent = stats.entregues || 0;
    document.getElementById('stat-pendentes').textContent = stats.pendentes || 0;
    document.getElementById('stat-alertas').textContent = stats.alertas || 0;
    document.getElementById('stat-atrasados').textContent = stats.atrasados || 0;
    document.getElementById('stat-devolvidos').textContent = stats.devolvidos || 0;
    document.getElementById('stat-erros').textContent = stats.erros || 0;
}

function adicionarUltimo(ultimo) {
    if (!ultimo) return;
    
    const tbody = document.getElementById('ultimos-body');
    if (tbody.rows.length === 1 && tbody.rows[0].cells[0].textContent.includes('Aguardando')) {
        tbody.innerHTML = '';
    }
    
    const row = tbody.insertRow(0);
    let statusClass = '';
    if (ultimo.status.includes('ENTREGUE')) statusClass = 'status-entregue';
    else if (ultimo.status.includes('ATRASADO')) statusClass = 'status-atrasado';
    else if (ultimo.status.includes('PREVISÃO')) statusClass = 'status-alerta';
    else if (ultimo.status.includes('DEVOLVIDO')) statusClass = 'status-devolvido';
    else statusClass = 'status-transito';
    
    let statusDisplay = ultimo.status.length > 35 ? ultimo.status.substring(0, 32) + '...' : ultimo.status;
    let clienteDisplay = (ultimo.destinatario || '-').length > 25 ? (ultimo.destinatario || '-').substring(0, 22) + '...' : (ultimo.destinatario || '-');
    
    row.innerHTML = `
        <td>${ultimo.data_hora || ''}</td>
        <td>${ultimo.nota_fiscal || '-'}</td>
        <td title="${ultimo.destinatario || ''}">${clienteDisplay}</td>
        <td><span class="status-badge ${statusClass}">${statusDisplay}</span></td>
    `;
}

function atualizarResumo(stats) {
    const tbody = document.getElementById('resumo-body');
    tbody.innerHTML = '';
    
    const statuses = [
        { nome: '✅ ENTREGUE', cor: '#28a745', valor: stats.entregues },
        { nome: '⏳ EM TRÂNSITO', cor: '#ffc107', valor: stats.pendentes },
        { nome: '⚠️ ALERTA (1-3 dias)', cor: '#fd7e14', valor: stats.alertas },
        { nome: '🔴 ATRASADO', cor: '#dc3545', valor: stats.atrasados },
        { nome: '🔄 DEVOLVIDO', cor: '#dc3545', valor: stats.devolvidos },
        { nome: '❌ ERRO', cor: '#6c757d', valor: stats.erros }
    ];
    
    statuses.forEach(s => {
        if (s.valor > 0) {
            const row = tbody.insertRow();
            row.innerHTML = `<td style="font-weight: 500;">${s.nome}</td><td style="color: ${s.cor}; font-weight: 700;">${s.valor}</td>`;
        }
    });
    
    if (tbody.rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2">Aguardando...</td></tr>';
    }
}

function conectarSSE(processId) {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/stream/${processId}`);
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.tipo === 'atualizacao') {
            const percentual = (data.dados.progresso / data.dados.total * 100) || 0;
            document.getElementById('progress-bar').style.width = `${percentual}%`;
            atualizarDashboard(data.dados.stats);
            if (data.dados.ultimo) {
                adicionarUltimo(data.dados.ultimo);
                atualizarResumo(data.dados.stats);
            }
        } else if (data.tipo === 'inicio') {
            document.getElementById('status-mensagem').innerHTML = `🚀 Processando ${data.dados.total} pedidos...`;
            document.getElementById('ultimos-body').innerHTML = '';
            document.getElementById('resumo-body').innerHTML = '';
        } else if (data.tipo === 'concluido') {
            document.getElementById('status-mensagem').innerHTML = `✅ Concluído! ${data.dados.stats.entregues} entregues`;
            document.getElementById('btn-cancelar').style.display = 'none';
            document.getElementById('btn-novo').style.display = 'inline-block';
            carregarDownload();
        } else if (data.tipo === 'erro') {
            document.getElementById('status-mensagem').innerHTML = `❌ ${data.dados.mensagem}`;
            document.getElementById('btn-cancelar').style.display = 'none';
            document.getElementById('btn-novo').style.display = 'inline-block';
        } else if (data.tipo === 'cancelado') {
            document.getElementById('status-mensagem').innerHTML = `⏸️ Cancelado`;
            document.getElementById('btn-cancelar').style.display = 'none';
            document.getElementById('btn-novo').style.display = 'inline-block';
        }
    };
}

async function carregarDownload() {
    try {
        const res = await fetch(`/api/resultado/${processId}`);
        const data = await res.json();
        document.getElementById('download-area').innerHTML = `<a href="/api/download/${processId}/excel">📊 Baixar Relatório Excel</a>`;
    } catch(e) { console.error(e); }
}

async function iniciarProcessamento() {
    const fonte = document.querySelector('input[name="fonte"]:checked').value;
    const coluna_xml = document.getElementById('coluna_xml').value;
    const delay = document.getElementById('delay').value;
    
    const formData = new FormData();
    formData.append('fonte', fonte);
    formData.append('coluna_xml', coluna_xml);
    formData.append('delay', delay);
    
    if (fonte === 'arquivo') {
        const arquivo = document.getElementById('arquivo').files[0];
        if (!arquivo) { alert('Selecione um arquivo!'); return; }
        formData.append('arquivo', arquivo);
    }
    
    const btn = document.getElementById('btn-iniciar');
    btn.disabled = true;
    btn.textContent = '⏳ PROCESSANDO...';
    
    try {
        const res = await fetch('/api/processar', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.erro);
        
        processId = data.process_id;
        document.getElementById('form-area').classList.add('hidden');
        document.getElementById('progresso-area').classList.remove('hidden');
        document.getElementById('btn-cancelar').style.display = 'inline-block';
        conectarSSE(processId);
    } catch (err) {
        alert('Erro: ' + err.message);
        btn.disabled = false;
        btn.textContent = '▶ INICIAR';
    }
}

async function cancelarProcessamento() {
    if (!processId) return;
    await fetch(`/api/cancelar/${processId}`, { method: 'POST' });
}

function novoProcessamento() {
    if (eventSource) eventSource.close();
    if (processId) fetch(`/api/limpar/${processId}`, { method: 'DELETE' });
    
    document.getElementById('form-area').classList.remove('hidden');
    document.getElementById('progresso-area').classList.add('hidden');
    document.getElementById('arquivo').value = '';
    document.getElementById('download-area').innerHTML = '';
    document.getElementById('btn-iniciar').disabled = false;
    document.getElementById('btn-iniciar').textContent = '▶ INICIAR';
    document.getElementById('ultimos-body').innerHTML = '<tr><td colspan="4">Aguardando...</td></tr>';
    document.getElementById('resumo-body').innerHTML = '<tr><td colspan="2">Aguardando...</td></tr>';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('status-mensagem').innerHTML = '';
    atualizarDashboard({ entregues:0, pendentes:0, alertas:0, atrasados:0, devolvidos:0, erros:0 });
}