import streamlit as st
import pandas as pd
import re
import io
from datetime import timedelta

# --- 1. CONFIGURAÇÃO (Dependências de Colunas) ---
COLS_TURING = {
    'ID': ['Exibir ID', 'ID', 'Ticket'],
    'Descricao': ['Descrição', 'Description'],
    'Data': ['Data de criação', 'Created', 'Data Abertura'],
    'Setor': ['Nome do grupo designado', 'Grupo', 'Assignment Group']
}

COLS_CHERWELL = {
    'Equipe': ['Equipe Responsável', 'Team', 'Grupo'],
    'Data': ['Data Hora de Abertura', 'Created Date'],
    'Tipo': ['Assunto', 'Tipo', 'Resumo'], 
    'ID': ['Número', 'ID', 'Incident ID'],
    'Prazo': ['Resolver até', 'SLA', 'Due Date']
}

# --- 2. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Central de Incidentes", layout="wide", page_icon="📊")

st.title("📊 Central de Incidentes Unificada")
st.markdown("---")

# --- 3. FUNÇÕES AUXILIARES ---
def encontrar_coluna(df, opcoes_nomes):
    for nome in opcoes_nomes:
        if nome in df.columns:
            return nome
    return None

def validar_arquivo(df, requisitos):
    map_colunas = {}
    erros = []
    for chave, opcoes in requisitos.items():
        col_encontrada = encontrar_coluna(df, opcoes)
        if col_encontrada:
            map_colunas[chave] = col_encontrada
        else:
            if chave == 'Prazo': 
                map_colunas[chave] = None
            else:
                erros.append(f"Faltando: {opcoes}")
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
    except:
        return pd.NaT
    return pd.NaT

def extrair_falha_regex(texto):
    if not isinstance(texto, str): return "Não Identificado"
    padrao = r"(?:Tipo d?e? falha|Tp\.? falha|Falha):\s*(.*?)(?:\n|$)"
    match = re.search(padrao, texto, re.IGNORECASE)
    if match: return match.group(1).strip()
    return "Não Identificado"

def processar_sla(df, col_data, col_prazo_existente=None):
    df['Data_Abertura_Formatada'] = pd.to_datetime(df[col_data], dayfirst=True, errors='coerce')
    if df['Data_Abertura_Formatada'].isnull().all():
         df['Data_Abertura_Formatada'] = df[col_data].apply(limpar_data_pt)

    if col_prazo_existente and col_prazo_existente in df.columns:
        df['Prazo_SLA'] = pd.to_datetime(df[col_prazo_existente], dayfirst=True, errors='coerce')
        idx_na = df['Prazo_SLA'].isna()
        df.loc[idx_na, 'Prazo_SLA'] = df.loc[idx_na, 'Data_Abertura_Formatada'] + timedelta(hours=24)
    else:
        df['Prazo_SLA'] = df['Data_Abertura_Formatada'] + timedelta(hours=24)
    return df

def converter_df_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Unificado')
    return output.getvalue()

# --- 4. ÁREA DE UPLOAD (GRID vs EXPORT) ---

col_grid, col_gap, col_export = st.columns([1, 0.1, 1])

with col_grid:
    st.info("📂 **ÁREA DO GRID (TURING)**")
    st.markdown("Use aqui o arquivo descritivo (texto longo) extraído do Turing.")
    file_turing = st.file_uploader("Arraste o CSV do Turing aqui", type=['csv'], key="f1")

with col_export:
    st.warning("📊 **ÁREA DO EXPORT (CHERWELL)**")
    st.markdown("Use aqui o arquivo estruturado extraído do Cherwell.")
    file_cherwell = st.file_uploader("Arraste o CSV do Cherwell aqui", type=['csv'], key="f2")

# --- 5. PROCESSAMENTO E EXIBIÇÃO ---

if file_turing and file_cherwell:
    st.divider()
    with st.spinner("Processando e unificando bases de dados..."):
        try:
            # --- LEITURA ---
            try: df_turing = pd.read_csv(file_turing)
            except: df_turing = pd.read_csv(file_turing, sep=';')
            
            try: df_cherwell = pd.read_csv(file_cherwell)
            except: df_cherwell = pd.read_csv(file_cherwell, sep=';')

            # --- VALIDAÇÃO ---
            val_turing, map_turing = validar_arquivo(df_turing, COLS_TURING)
            val_cherwell, map_cherwell = validar_arquivo(df_cherwell, COLS_CHERWELL)

            if not val_turing:
                st.error(f"❌ Erro no arquivo Turing: {map_turing}")
                st.stop()
            if not val_cherwell:
                st.error(f"❌ Erro no arquivo Cherwell: {map_cherwell}")
                st.stop()

            # --- PROCESSAMENTO TURING ---
            df_turing['Tipo_Falha'] = df_turing[map_turing['Descricao']].apply(extrair_falha_regex)
            df_turing = processar_sla(df_turing, map_turing['Data'])
            df_turing['Setor'] = df_turing[map_turing['Setor']].fillna('Não Atribuído').astype(str).str.strip()
            
            df_turing_final = df_turing[[map_turing['ID'], 'Tipo_Falha', 'Setor', 'Data_Abertura_Formatada', 'Prazo_SLA']].copy()
            df_turing_final.columns = ['ID', 'Tipo_Falha', 'Setor', 'Data_Abertura', 'Prazo_SLA']
            df_turing_final['Origem'] = 'Turing'

            # --- PROCESSAMENTO CHERWELL ---
            df_cherwell['Tipo_Falha'] = df_cherwell[map_cherwell['Tipo']].astype(str).str.split('-').str[0].str.strip()
            df_cherwell = processar_sla(df_cherwell, map_cherwell['Data'], map_cherwell['Prazo'])
            df_cherwell['Setor'] = df_cherwell[map_cherwell['Equipe']].fillna('Não Atribuído').astype(str).str.strip()
            
            df_cherwell_final = df_cherwell[[map_cherwell['ID'], 'Tipo_Falha', 'Setor', 'Data_Abertura_Formatada', 'Prazo_SLA']].copy()
            df_cherwell_final.columns = ['ID', 'Tipo_Falha', 'Setor', 'Data_Abertura', 'Prazo_SLA']
            df_cherwell_final['Origem'] = 'Cherwell'

            # --- UNIFICAÇÃO ---
            df_unificado = pd.concat([df_turing_final, df_cherwell_final], ignore_index=True)
            agora = pd.Timestamp.now()
            df_unificado['Status_SLA'] = df_unificado['Prazo_SLA'].apply(lambda x: '🚨 Vencido' if pd.notnull(x) and x < agora else '✅ No Prazo')
            df_unificado = df_unificado.sort_values(by='Data_Abertura', ascending=False)

            # --- 6. ÁREA DE FILTROS (MAIN PAGE) ---
            st.subheader("🔍 Filtros de Análise")
            
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                lista_setores = sorted(df_unificado['Setor'].unique())
                padrao = ['TCLOUD-DEVOPS-PROTHEUS'] if 'TCLOUD-DEVOPS-PROTHEUS' in lista_setores else lista_setores
                setores_selecionados = st.multiselect("Filtrar por Setor:", options=lista_setores, default=padrao)

            with col_f2:
                origens_selecionadas = st.multiselect("Filtrar por Origem:", options=df_unificado['Origem'].unique(), default=df_unificado['Origem'].unique())

            # Aplicação dos Filtros
            if not setores_selecionados or not origens_selecionadas:
                st.warning("Selecione pelo menos um setor e uma origem.")
                st.stop()

            df_view = df_unificado[
                (df_unificado['Setor'].isin(setores_selecionados)) & 
                (df_unificado['Origem'].isin(origens_selecionadas))
            ]

            # --- 7. DASHBOARD ---
            st.divider()
            
            # Métricas
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Filtrado", len(df_view))
            m2.metric("SLA Vencido", len(df_view[df_view['Status_SLA'] == '🚨 Vencido']))
            m3.metric("Setores", len(setores_selecionados))
            m4.metric("Origens", ", ".join(origens_selecionadas))

            # Gráficos
            st.subheader("📈 Análise Visual")
            tab1, tab2 = st.tabs(["Por Tipo de Falha", "Por Setor"])
            
            with tab1:
                if not df_view.empty:
                    st.bar_chart(df_view['Tipo_Falha'].value_counts(), color="#FF4B4B")
                else:
                    st.info("Sem dados.")

            with tab2:
                if not df_view.empty:
                    st.bar_chart(df_view['Setor'].value_counts(), color="#0068C9")
                else:
                    st.info("Sem dados.")

            # Tabela
            with st.expander("📋 Ver Dados Detalhados", expanded=True):
                st.dataframe(df_view, use_container_width=True)

            # Download
            excel_data = converter_df_para_excel(df_view)
            st.download_button("📥 Baixar Planilha Filtrada (.xlsx)", excel_data, "Relatorio_Filtrado.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        except Exception as e:
            st.error(f"Erro ao processar: {e}")

else:
    st.info("👆 Por favor, carregue os dois arquivos CSV acima para gerar o dashboard.")