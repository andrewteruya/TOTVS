import streamlit as st
import pandas as pd
import re
import io
from datetime import timedelta

# --- 1. Configurações e Funções Auxiliares ---
st.set_page_config(page_title="Central de Incidentes Unificada", layout="wide", page_icon="💻")

MESES_PT = {
    'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04', 'mai': '05', 'jun': '06',
    'jul': '07', 'ago': '08', 'set': '09', 'out': '10', 'nov': '11', 'dez': '12'
}

def limpar_data_pt(data_str):
    """Converte datas como '17 de dez. de 2025 14:46:02' para datetime"""
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
    """Extrai o tipo de falha de textos longos (Arquivo turing)"""
    if not isinstance(texto, str): return "Não Identificado"
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
st.title("💻 Unificador de Incidentes e SLA")
st.markdown("Faça o upload dos dois arquivos. O sistema filtrará automaticamente o time **TCLOUD-DEVOPS-PROTHEUS** no arquivo cherwell.")

col_up1, col_up2 = st.columns(2)

with col_up1:
    st.subheader("📂 Arquivo 1: Turing (Descritivo)")
    file_turing = st.file_uploader("Upload CSV turing", type=['csv'], key="f1")

with col_up2:
    st.subheader("📂 Arquivo 2: Cherwell (Estruturado)")
    file_cherwell = st.file_uploader("Upload CSV cherwell", type=['csv'], key="f2")

if file_turing and file_cherwell:
    st.divider()
    if st.button("Processar e Unificar Arquivos 🚀"):
        try:
            # --- PROCESSAMENTO ARQUIVO turing (TCloud) ---
            try:
                df_turing = pd.read_csv(file_turing)
            except:
                df_turing = pd.read_csv(file_turing, sep=';')
            
            # Normalização turing
            df_turing['Tipo_Falha_Unificado'] = df_turing['Descrição'].apply(extrair_falha_regex)
            df_turing = processar_sla(df_turing, 'Data de criação') # Calcula data + 24h
            
            # Seleciona e renomeia
            df_turing_final = df_turing[['Exibir ID', 'Tipo_Falha_Unificado', 'Data_Abertura_Formatada', 'Prazo_SLA']].copy()
            df_turing_final.columns = ['ID', 'Tipo_Falha', 'Data_Abertura', 'Prazo_SLA']
            df_turing_final['Origem'] = 'turing (TCloud)'

            # --- PROCESSAMENTO ARQUIVO cherwell (Sistema Externo) ---
            try:
                df_cherwell = pd.read_csv(file_cherwell)
            except:
                df_cherwell = pd.read_csv(file_cherwell, sep=';')

            # >>> FILTRO DE TIME RESPONSÁVEL <<<
            if 'Equipe Responsável' in df_cherwell.columns:
                filtro_time = 'TCLOUD-DEVOPS-PROTHEUS'
                # Filtra apenas o time desejado
                df_cherwell = df_cherwell[df_cherwell['Equipe Responsável'] == filtro_time].copy()
                st.toast(f"Filtro aplicado: {len(df_cherwell)} registros encontrados para {filtro_time} no arquivo cherwell.")
            else:
                st.warning("Coluna 'Equipe Responsável' não encontrada no arquivo cherwell. O filtro não foi aplicado.")

            # Identifica colunas
            col_tipo_cherwell = 'Assunto' if 'Assunto' in df_cherwell.columns else df_cherwell.columns[0]
            col_id_cherwell = 'Número' if 'Número' in df_cherwell.columns else 'ID'
            col_data_cherwell = 'Data Hora de Abertura'
            col_prazo_cherwell = 'Resolver até' 

            # Normalização cherwell
            # Limpa o texto antes do primeiro hífen (ex: "Incidente - Erro..." vira "Incidente")
            # Ou se quiser o conteúdo DEPOIS do hífen, mude para .str[1] se fizer sentido.
            # Aqui mantivemos a lógica de pegar a primeira parte ou o texto todo se não tiver hífen.
            df_cherwell['Tipo_Falha_Unificado'] = df_cherwell[col_tipo_cherwell].astype(str).str.split('-').str[0].str.strip()
            
            df_cherwell = processar_sla(df_cherwell, col_data_cherwell, col_prazo_cherwell)

            # Seleciona e renomeia
            df_cherwell_final = df_cherwell[[col_id_cherwell, 'Tipo_Falha_Unificado', 'Data_Abertura_Formatada', 'Prazo_SLA']].copy()
            df_cherwell_final.columns = ['ID', 'Tipo_Falha', 'Data_Abertura', 'Prazo_SLA']
            df_cherwell_final['Origem'] = 'cherwell System'

            # --- UNIFICAÇÃO ---
            df_unificado = pd.concat([df_turing_final, df_cherwell_final], ignore_index=True)

            # Cálculo de Status SLA
            agora = pd.Timestamp.now()
            df_unificado['Status_SLA'] = df_unificado['Prazo_SLA'].apply(lambda x: '🚨 Vencido' if pd.notnull(x) and x < agora else '✅ No Prazo')
            
            # Ordenar por data
            df_unificado = df_unificado.sort_values(by='Data_Abertura', ascending=False)

            # --- EXIBIÇÃO ---
            st.success(f"Unificação concluída! Total de incidentes filtrados e unidos: {len(df_unificado)}")

            # Métricas
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Geral", len(df_unificado))
            c2.metric("Vencidos", len(df_unificado[df_unificado['Status_SLA'] == '🚨 Vencido']))
            c3.metric("Origem Turing", len(df_turing_final))
            c4.metric("Origem Cherwell (Filtrado)", len(df_cherwell_final))

            st.subheader("Tabela Unificada")
            st.dataframe(df_unificado, use_container_width=True)

            # Gráfico
            st.subheader("Top 5 Tipos de Falha")
            if not df_unificado.empty:
                st.bar_chart(df_unificado['Tipo_Falha'].value_counts().head(5))
            else:
                st.info("Nenhum dado para exibir no gráfico.")

            # Download
            excel_data = converter_df_para_excel(df_unificado)
            st.download_button(
                label="📥 Baixar Relatório Unificado (.xlsx)",
                data=excel_data,
                file_name="incidentes_unificados_filtrados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
            st.write("Verifique se as colunas 'Equipe Responsável', 'Data Hora de Abertura' e 'Exibir ID' existem nos arquivos.")