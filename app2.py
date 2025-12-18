import streamlit as st
import pandas as pd
import re
import io
from datetime import timedelta

# --- 1. Configurações e Funções Auxiliares ---
st.set_page_config(page_title="Central de Incidentes Unificada", layout="wide", page_icon="🧩")

# Dicionário para traduzir datas por extenso (comum no arquivo Grid)
MESES_PT = {
    'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04', 'mai': '05', 'jun': '06',
    'jul': '07', 'ago': '08', 'set': '09', 'out': '10', 'nov': '11', 'dez': '12'
}

def limpar_data_pt(data_str):
    """Converte '17 de dez. de 2025 14:46:02' para datetime"""
    if not isinstance(data_str, str): return pd.NaT
    try:
        # Remove 'de ' e pontos
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
    """Extrai o tipo de falha de textos longos (Arquivo Grid)"""
    if not isinstance(texto, str): return "Não Identificado"
    # Procura por 'Tipo da falha:' e pega o texto seguinte
    padrao = r"(?:Tipo d?e? falha|Tp\.? falha|Falha):\s*(.*?)(?:\n|$)"
    match = re.search(padrao, texto, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "Não Identificado"

def processar_sla(df, col_data, col_prazo_existente=None):
    """Calcula o prazo de 24h se não existir, ou usa o existente"""
    # Converte coluna de data de abertura
    df['Data_Abertura_Formatada'] = pd.to_datetime(df[col_data], dayfirst=True, errors='coerce')
    
    # Se a conversão falhou (formato texto pt-br), tenta o parser customizado
    if df['Data_Abertura_Formatada'].isnull().all():
         df['Data_Abertura_Formatada'] = df[col_data].apply(limpar_data_pt)

    # Define o Prazo SLA
    if col_prazo_existente and col_prazo_existente in df.columns:
        df['Prazo_SLA'] = pd.to_datetime(df[col_prazo_existente], dayfirst=True, errors='coerce')
        # Preenche vazios com regra de 24h
        idx_na = df['Prazo_SLA'].isna()
        df.loc[idx_na, 'Prazo_SLA'] = df.loc[idx_na, 'Data_Abertura_Formatada'] + timedelta(hours=24)
    else:
        # Se não tem coluna de prazo, calcula +24h fixo
        df['Prazo_SLA'] = df['Data_Abertura_Formatada'] + timedelta(hours=24)
        
    return df

def converter_df_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Unificado')
    return output.getvalue()

# --- 2. Interface Principal ---
st.title("🧩 Unificador de Incidentes e SLA")
st.markdown("Faça o upload dos dois padrões de arquivo para gerar um relatório unificado.")

col_up1, col_up2 = st.columns(2)

with col_up1:
    st.subheader("📂 Arquivo 1: Grid (Descritivo)")
    file_grid = st.file_uploader("Upload CSV Grid", type=['csv'], key="f1")

with col_up2:
    st.subheader("📂 Arquivo 2: Export (Estruturado)")
    file_export = st.file_uploader("Upload CSV Export", type=['csv'], key="f2")

if file_grid and file_export:
    st.divider()
    if st.button("Processar e Unificar Arquivos 🚀"):
        try:
            # --- PROCESSAMENTO ARQUIVO GRID (Com Regex) ---
            df_grid = pd.read_csv(file_grid)
            
            # Normalização Grid
            df_grid['Tipo_Falha_Unificado'] = df_grid['Descrição'].apply(extrair_falha_regex)
            df_grid = processar_sla(df_grid, 'Data de criação') # Calcula data + 24h
            
            # Seleciona e renomeia para o padrão final
            df_grid_final = df_grid[['Exibir ID', 'Tipo_Falha_Unificado', 'Data_Abertura_Formatada', 'Prazo_SLA']].copy()
            df_grid_final.columns = ['ID', 'Tipo_Falha', 'Data_Abertura', 'Prazo_SLA']
            df_grid_final['Origem'] = 'Grid (TCloud)'

            # --- PROCESSAMENTO ARQUIVO EXPORT (Estruturado) ---
            try:
                df_export = pd.read_csv(file_export)
            except:
                df_export = pd.read_csv(file_export, sep=';')

            # Tenta identificar a coluna de Assunto/Tipo automaticamente
            col_tipo_export = 'Assunto' if 'Assunto' in df_export.columns else df_export.columns[0]
            col_id_export = 'Número' if 'Número' in df_export.columns else 'ID'
            col_data_export = 'Data Hora de Abertura'
            col_prazo_export = 'Resolver até' # Coluna que já existe nesse arquivo

            # Normalização Export
            # Aqui assumimos que a coluna 'Assunto' ou 'Tipo' JÁ É o tipo da falha. 
            # Se precisar limpar (ex: remover "Incidente - "), pode adicionar um .apply(lambda x: x...)
            df_export['Tipo_Falha_Unificado'] = df_export[col_tipo_export].astype(str).str.split('-').str[0].str.strip()
            
            df_export = processar_sla(df_export, col_data_export, col_prazo_export)

            # Seleciona e renomeia
            df_export_final = df_export[[col_id_export, 'Tipo_Falha_Unificado', 'Data_Abertura_Formatada', 'Prazo_SLA']].copy()
            df_export_final.columns = ['ID', 'Tipo_Falha', 'Data_Abertura', 'Prazo_SLA']
            df_export_final['Origem'] = 'Export System'

            # --- UNIFICAÇÃO ---
            df_unificado = pd.concat([df_grid_final, df_export_final], ignore_index=True)

            # Análise de SLA (Vencido ou No Prazo) - Comparando com Agora (simulação) ou Data Atual
            agora = pd.Timestamp.now()
            df_unificado['Status_SLA'] = df_unificado['Prazo_SLA'].apply(lambda x: '🚨 Vencido' if x < agora else '✅ No Prazo')
            
            # Ordenar por data
            df_unificado = df_unificado.sort_values(by='Data_Abertura', ascending=False)

            # --- EXIBIÇÃO ---
            st.success(f"Sucesso! {len(df_unificado)} incidentes unificados.")

            # Métricas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Incidentes", len(df_unificado))
            m2.metric("Vencidos (SLA)", len(df_unificado[df_unificado['Status_SLA'] == '🚨 Vencido']))
            m3.metric("Origem Grid / Export", f"{len(df_grid_final)} / {len(df_export_final)}")

            st.subheader("Tabela Unificada")
            st.dataframe(df_unificado)

            # Gráfico Rápido
            st.subheader("Top 5 Tipos de Falha")
            top_falhas = df_unificado['Tipo_Falha'].value_counts().head(5)
            st.bar_chart(top_falhas)

            # Download
            excel_data = converter_df_para_excel(df_unificado)
            st.download_button(
                label="📥 Baixar Relatório Unificado (.xlsx)",
                data=excel_data,
                file_name="incidentes_unificados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
            st.write("Dica: Verifique se os nomes das colunas nos arquivos correspondem ao esperado (Exibir ID, Data de criação, Assunto, Número).")