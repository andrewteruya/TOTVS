import streamlit as st
import pandas as pd
import re
import io
import sqlite3
from datetime import timedelta

# --- 1. CONFIGURAÇÃO E BANCO DE DADOS ---
st.set_page_config(page_title="Gestão de Incidentes + Relatórios", layout="wide", page_icon="📊")

DB_FILE = "incidentes_full_abertos.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidentes (
            id TEXT PRIMARY KEY,
            tipo_falha TEXT,
            setor TEXT,
            data_abertura TIMESTAMP,
            prazo_sla TIMESTAMP,
            origem TEXT,
            status_sla TEXT,
            descricao TEXT
        )
    ''')
    conn.commit()
    conn.close()

def salvar_no_banco(df):
    if df.empty: return 0
    conn = sqlite3.connect(DB_FILE)
    df_save = df.copy()
    
    # Tratamento de tipos
    df_save['data_abertura'] = df_save['Data_Abertura'].astype(str)
    df_save['prazo_sla'] = df_save['Prazo_SLA'].astype(str)
    df_save['descricao'] = df_save['Descricao_Completa'].astype(str)
    
    dados = df_save[['ID', 'Tipo_Falha', 'Setor', 'data_abertura', 'prazo_sla', 'Origem', 'Status_SLA', 'descricao']].values.tolist()
    
    c = conn.cursor()
    count_novos = 0
    for row in dados:
        try:
            c.execute('''
                INSERT OR REPLACE INTO incidentes (id, tipo_falha, setor, data_abertura, prazo_sla, origem, status_sla, descricao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', row)
            if c.rowcount > 0: count_novos += 1
        except:
            pass
    conn.commit()
    conn.close()
    return count_novos

def carregar_do_banco():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql("SELECT * FROM incidentes", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    
    if not df.empty:
        df['data_abertura'] = pd.to_datetime(df['data_abertura'], errors='coerce')
        df['prazo_sla'] = pd.to_datetime(df['prazo_sla'], errors='coerce')
        df.columns = ['ID', 'Tipo_Falha', 'Setor', 'Data_Abertura', 'Prazo_SLA', 'Origem', 'Status_SLA', 'Descricao_Completa']
    return df

init_db()

# --- 2. CONFIGURAÇÕES DE COLUNAS ---
COLS_TURING = {
    'ID': ['Exibir ID', 'ID', 'Ticket'],
    'Descricao': ['Descrição', 'Description'],
    'Data': ['Data de criação', 'Created'],
    'Setor': ['Nome do grupo designado', 'Grupo']
}

COLS_CHERWELL = {
    'Equipe': ['Equipe Responsável', 'Team'],
    'Data': ['Data Hora de Abertura', 'Created Date'],
    'Tipo': ['Assunto', 'Tipo', 'Resumo'], 
    'ID': ['Número', 'ID'],
    'Prazo': ['Resolver até', 'SLA'],
    'Descricao': ['Descrição', 'Description', 'Detalhes']
}

# --- 3. FUNÇÕES AUXILIARES ---
def encontrar_coluna(df, opcoes_nomes):
    for nome in opcoes_nomes:
        if nome in df.columns: return nome
    return None

def validar_arquivo(df, requisitos):
    map_colunas = {}
    erros = []
    for chave, opcoes in requisitos.items():
        col_encontrada = encontrar_coluna(df, opcoes)
        if col_encontrada: 
            map_colunas[chave] = col_encontrada
        else:
            if chave in ['Prazo']: 
                map_colunas[chave] = None
            else:
                erros.append(f"Faltando coluna: {opcoes}")
    return (False, erros) if erros else (True, map_colunas)

def limpar_data_pt(data_str):
    MESES_PT = {'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04', 'mai': '05', 'jun': '06',
                'jul': '07', 'ago': '08', 'set': '09', 'out': '10', 'nov': '11', 'dez': '12'}
    if not isinstance(data_str, str): return pd.NaT
    try:
        clean = data_str.replace('de ', '').replace('.', '').lower()
        parts = clean.split()
        if len(parts) >= 3:
            day, month_txt, year = parts[0], parts[1], parts[2]
            time = parts[3] if len(parts) > 3 else "00:00:00"
            month_num = MESES_PT.get(month_txt[:3], '01')
            return pd.to_datetime(f"{year}-{month_num}-{day} {time}")
    except: return pd.NaT
    return pd.NaT

def processar_datas(df, col_abertura):
    df['Data_Abertura_Formatada'] = pd.to_datetime(df[col_abertura], dayfirst=True, errors='coerce')
    if df['Data_Abertura_Formatada'].isnull().all():
         df['Data_Abertura_Formatada'] = df[col_abertura].apply(limpar_data_pt)
    return df

def extrair_falha_regex(texto):
    if not isinstance(texto, str): return "Não Identificado"
    padrao = r"(?:Tipo d?e? falha|Tp\.? falha|Falha):\s*(.*?)(?:\n|$)"
    match = re.search(padrao, texto, re.IGNORECASE)
    return match.group(1).strip() if match else "Não Identificado"

def converter_df_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Unificado')
    return output.getvalue()

# --- 4. MODAL DE DETALHES (OTIMIZADO - SEM ESPAÇOS EXTRAS) ---
@st.dialog("📋 Detalhes do Incidente", width="large")
def modal_detalhes(registro):
    # Linha 1: Dados principais compactados
    c1, c2, c3, c4 = st.columns([1.5, 2, 1.5, 1.5])
    
    # Formata Data Curta
    data_formatada = registro['Data_Abertura']
    if hasattr(data_formatada, 'strftime'):
        data_formatada = data_formatada.strftime('%d/%m/%Y %H:%M')

    c1.markdown(f"**🆔 ID:** `{registro['ID']}`")
    c2.markdown(f"**🏷️ Tipo:** {registro['Tipo_Falha']}")
    c3.markdown(f"**📅:** {data_formatada}")
    
    status_cor = "red" if registro['Status_SLA'] == '🚨 Vencido' else "green"
    c4.markdown(f"**SLA:** :{status_cor}[{registro['Status_SLA']}]")
    
    # Label simples para economizar espaço do st.divider e headers
    st.caption(f"📝 **Descrição Completa** (Origem: {registro['Origem']})")
    
    texto = registro['Descricao_Completa']
    if pd.isna(texto) or texto == "nan":
        st.warning("Sem descrição disponível.")
    else:
        # Altura aumentada para 650px para aproveitar o espaço ganho
        with st.container(height=650):
            st.code(texto, language="text", wrap_lines=True)

# --- 5. INTERFACE UNIFICADA ---
st.title("📉 Dashboard de Incidentes")

# ================= SEÇÃO DE UPLOAD (TOPO) =================
with st.expander("📥 Importar Dados (Clique para abrir/fechar)", expanded=True):
    st.caption("Carregue os arquivos para atualizar o banco e recarregar a tela.")
    c_up1, c_up2 = st.columns(2)
    f_t = c_up1.file_uploader("Arquivo Turing (Grid)", type=['csv'], key="up_turing")
    f_c = c_up2.file_uploader("Arquivo Cherwell (Export)", type=['csv'], key="up_cherwell")
    
    if st.button("💾 Processar e Salvar no Banco", type="primary"):
        if f_t and f_c:
            try:
                with st.spinner("Processando..."):
                    # Ler
                    try: df_t = pd.read_csv(f_t)
                    except: df_t = pd.read_csv(f_t, sep=';')
                    try: df_c = pd.read_csv(f_c)
                    except: df_c = pd.read_csv(f_c, sep=';')
                    
                    # Validar
                    vt, mt = validar_arquivo(df_t, COLS_TURING)
                    vc, mc = validar_arquivo(df_c, COLS_CHERWELL)
                    
                    if not vt or not vc:
                        st.error("Erro nas colunas.")
                    else:
                        # Processa Turing
                        df_t['Tipo_Falha'] = df_t[mt['Descricao']].apply(extrair_falha_regex)
                        df_t = processar_datas(df_t, mt['Data'])
                        df_t['Setor'] = df_t[mt['Setor']].fillna('N/A').astype(str).str.strip()
                        df_t['Descricao_Completa'] = df_t[mt['Descricao']]
                        df_t['Prazo_SLA'] = df_t['Data_Abertura_Formatada'] + timedelta(hours=24)
                        
                        df_t_fin = df_t[[mt['ID'], 'Tipo_Falha', 'Setor', 'Data_Abertura_Formatada', 'Prazo_SLA', 'Descricao_Completa']].copy()
                        df_t_fin.columns = ['ID', 'Tipo_Falha', 'Setor', 'Data_Abertura', 'Prazo_SLA', 'Descricao_Completa']
                        df_t_fin['Origem'] = 'Turing'
                        
                        # Processa Cherwell
                        df_c['Tipo_Falha'] = df_c[mc['Tipo']].astype(str).str.split('-').str[0].str.strip()
                        df_c = processar_datas(df_c, mc['Data'])
                        df_c['Setor'] = df_c[mc['Equipe']].fillna('N/A').astype(str).str.strip()
                        df_c['Descricao_Completa'] = df_c[mc['Descricao']]
                        if mc['Prazo']: df_c['Prazo_SLA'] = pd.to_datetime(df_c[mc['Prazo']], dayfirst=True, errors='coerce')
                        else: df_c['Prazo_SLA'] = df_c['Data_Abertura_Formatada'] + timedelta(hours=24)
                        
                        df_c_fin = df_c[[mc['ID'], 'Tipo_Falha', 'Setor', 'Data_Abertura_Formatada', 'Prazo_SLA', 'Descricao_Completa']].copy()
                        df_c_fin.columns = ['ID', 'Tipo_Falha', 'Setor', 'Data_Abertura', 'Prazo_SLA', 'Descricao_Completa']
                        df_c_fin['Origem'] = 'Cherwell'
                        
                        # Unifica
                        df_final = pd.concat([df_t_fin, df_c_fin], ignore_index=True)
                        agora = pd.Timestamp.now()
                        df_final['Status_SLA'] = df_final['Prazo_SLA'].apply(lambda x: '🚨 Vencido' if pd.notnull(x) and x < agora else '✅ No Prazo')
                        
                        salvar_no_banco(df_final)
                        st.success("Dados salvos! Recarregando...")
                        st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
        else:
            st.warning("Insira os dois arquivos.")

st.divider()

# ================= SEÇÃO DASHBOARD (Relatórios) =================
st.header("📊 Visão Geral")

df_historico = carregar_do_banco()

if df_historico.empty:
    st.info("Banco vazio.")
else:
    # Recalcula SLA
    agora = pd.Timestamp.now()
    df_historico['Status_SLA'] = df_historico.apply(lambda row: "✅ No Prazo" if pd.isna(row['Prazo_SLA']) or row['Prazo_SLA'] >= agora else "🚨 Vencido", axis=1)

    # --- FILTROS ---
    with st.expander("🔍 Filtros de Visualização", expanded=False):
        c1, c2 = st.columns(2)
        setores = sorted(df_historico['Setor'].dropna().unique())
        defaults = [s for s in setores if 'DEVOPS-PROTHEUS' in s or 'Devops Protheus' in s]
        if not defaults: defaults = setores
        
        sel_setor = c1.multiselect("Setor", setores, default=defaults)
        sel_origem = c2.multiselect("Origem", df_historico['Origem'].unique(), default=df_historico['Origem'].unique())
    
    df_view = df_historico[
        (df_historico['Setor'].isin(sel_setor)) &
        (df_historico['Origem'].isin(sel_origem))
    ]
    
    if not df_view.empty:
        # 1. KPIs
        total = len(df_view)
        vencidos = len(df_view[df_view['Status_SLA']=='🚨 Vencido'])
        no_prazo = len(df_view[df_view['Status_SLA']=='✅ No Prazo'])
        
        c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
        c_kpi1.metric("Total Incidentes", total)
        c_kpi2.metric("No Prazo", no_prazo, delta="OK")
        c_kpi3.metric("Vencidos", vencidos, delta_color="inverse")
        
        st.divider()

        # === 2. RELATÓRIO: QUANTIDADE POR TIPO ===
        st.subheader("📈 Relatório: Quantidade por Tipo de Falha")
        
        col_rel1, col_rel2 = st.columns([1, 2])
        
        with col_rel1:
            df_contagem = df_view['Tipo_Falha'].value_counts().reset_index()
            df_contagem.columns = ['Tipo de Falha', 'Quantidade']
            st.dataframe(df_contagem, use_container_width=True, hide_index=True)
            
        with col_rel2:
            st.bar_chart(df_view['Tipo_Falha'].value_counts(), color="#FF4B4B", horizontal=True)

        st.divider()

        # 3. LISTA DETALHADA
        st.subheader("📋 Lista Detalhada de Incidentes")
        
        filtro_tabela = st.radio("Visualizar:", ["Todos", "Apenas No Prazo", "Apenas Vencidos"], horizontal=True)
        
        df_table = df_view.copy()
        if filtro_tabela == "Apenas No Prazo":
            df_table = df_view[df_view['Status_SLA'] == '✅ No Prazo']
        elif filtro_tabela == "Apenas Vencidos":
            df_table = df_view[df_view['Status_SLA'] == '🚨 Vencido']

        event = st.dataframe(
            df_table[['ID', 'Tipo_Falha', 'Setor', 'Data_Abertura', 'Status_SLA', 'Origem']].sort_values('Data_Abertura', ascending=False),
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            height=400,
            hide_index=True
        )
        
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            reg = df_table.sort_values('Data_Abertura', ascending=False).iloc[idx]
            modal_detalhes(reg)
            
        st.divider()
        st.download_button("📥 Baixar Excel Completo", converter_df_para_excel(df_view), "Incidentes.xlsx")
        
    else:
        st.info("Nenhum dado com os filtros atuais.")