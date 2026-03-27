# 🚚 SSW Rastreamento de Entregas

Sistema desenvolvido em **Python + Flask** para realizar o **rastreamento automático de entregas da transportadora SSW** utilizando a **chave XML da Nota Fiscal (NF-e)**.

O sistema consulta o rastreamento diretamente no site da SSW, coleta as informações da entrega e gera um **relatório completo em Excel**, permitindo acompanhar o status das entregas.

---

# 📌 Funcionalidades

✔ Consulta automática de rastreamento pela **chave XML da NF-e**

✔ Extração de informações da página de rastreamento:

- Nome do destinatário  
- Número da Nota Fiscal  
- Status da entrega  
- Data estimada de entrega  

✔ Processamento em lote através de:

- Planilha Excel
- Google Sheets

✔ Classificação automática das entregas:

- Entregue
- Pendente
- Em alerta (próximo da data prometida)
- Atrasado
- Devolvido
- Erro na consulta

✔ Sistema de **alerta preventivo**

Quando faltam **3 dias ou menos para a data prometida** e a entrega ainda não foi realizada, o sistema marca como **ALERTA**.

✔ Exportação automática dos resultados em **Excel**

✔ Interface web simples para acompanhamento do processamento.

---

# 🔎 Como funciona o rastreamento

O sistema consulta o rastreamento da transportadora **SSW** através da seguinte estrutura de URL:https://ssw.inf.br/app/tracking/CHAVE\_XML\_DA\_NFE


Exemplo:https://ssw.inf.br/app/tracking/35191234567890000123450010000012341000012345


A página retornada é analisada e o sistema extrai automaticamente os dados de rastreamento.

---

# 📊 Fluxo do sistema

1️⃣ Usuário envia uma planilha com as **chaves XML das NF-e**

2️⃣ O sistema percorre cada chave

3️⃣ Consulta o rastreamento no site da **SSW**

4️⃣ Extrai os dados da página HTML

5️⃣ Classifica o status da entrega

6️⃣ Gera um **relatório final em Excel**

---

# 📥 Entrada de dados

O sistema pode receber dados de duas formas:

### 📄 Arquivo Excel

Planilha contendo uma coluna com a **chave XML da NF-e**.

### 📊 Google Sheets

O sistema também pode ler automaticamente dados de uma planilha no Google Sheets.

---

# 📤 Resultado

Após o processamento o sistema gera:

✔ Planilha Excel com os dados atualizados  
✔ Status das entregas  
✔ Estatísticas do processamento

---

# 📊 Status monitorados

O sistema classifica automaticamente os pedidos em:

| Status | Descrição |
|------|------|
| ENTREGUE | Entrega concluída |
| PENDENTE | Entrega ainda em transporte |
| ALERTA | Faltam 3 dias ou menos para a data prometida |
| ATRASADO | Data prometida ultrapassada |
| DEVOLVIDO | Pedido devolvido |
| ERRO | Falha na consulta |

---


# 🛠 Tecnologias utilizadas

- Python
- Flask
- Pandas
- BeautifulSoup
- Google Sheets API
- OpenPyXL

---

# 📌 Observações

Este sistema foi desenvolvido para **automatizar o acompanhamento de entregas da transportadora SSW**, facilitando o controle logístico e identificação de possíveis atrasos.

---

# 👨‍💻 Autor

Desenvolvido por **Helton Cardoso**



