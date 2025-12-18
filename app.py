# python -m pip install streamlit pandas openpyxl
# 
#
import streamlit as st
import pandas as pd
import re
import io

# --- 1. Configuração da Página ---
st.set_page_config(page_title="Agente de Limpeza de Logs", layout="wide")
st.title("🤖 Agente de Extração de Falhas")
st.markdown("""
Este agente recebe um CSV, procura padrões de **'Tipo de falha:'** e gera uma planilha limpa pronta para análise.
""")

# --- 2. Lógica do "Cérebro" (A função de extração) ---
def extrair_falha_inteligente(texto):
    """
    Extrai o valor do campo 'Tipo da falha' mesmo que esteja na linha de baixo.
    """
    if not isinstance(texto, str):
        return None
    
    # EXPLICAÇÃO DO REGEX:
    # Tipo da falha:  -> Procura essa frase exata
    # \s+             -> Pula qualquer espaço ou QUEBRA DE LINHA que vier depois
    # ([^\n]+)        -> Captura tudo até encontrar a próxima quebra de linha (o fim da frase do erro)
    padrao = r"Tipo da falha:\s+([^\n]+)"
    
    match = re.search(padrao, texto, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def converter_df_para_excel(df):
    """Converte o DataFrame para bytes de Excel em memória"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados Processados')
    return output.getvalue()

# --- 3. Interface do Usuário (Frontend) ---

# Passo 1: Upload
uploaded_file = st.file_uploader("Jogue seu CSV aqui", type=["csv"])

if uploaded_file is not None:
    try:
        # Lê o CSV (tenta detectar separador automaticamente ou usa ,)
        try:
            df = pd.read_csv(uploaded_file)
        except:
            df = pd.read_csv(uploaded_file, sep=';')
            
        st.success("Arquivo carregado com sucesso!")
        
        # Mostra os primeiros dados crus
        st.subheader("1. Visualização dos Dados Crus")
        st.dataframe(df.head())

        # Passo 2: Seleção da Coluna
        colunas = df.columns.tolist()
        coluna_alvo = st.selectbox("Em qual coluna está o texto bagunçado?", colunas)

        if st.button("Executar Agente de Limpeza 🚀"):
            with st.spinner('O Agente está lendo e extraindo os padrões...'):
                # Aplica a lógica
                nome_nova_coluna = 'Falha_Identificada'
                df[nome_nova_coluna] = df[coluna_alvo].apply(extrair_falha_inteligente)
                
                # Separa em Dataframes de Sucesso e Falha (para auditoria)
                df_sucesso = df[df[nome_nova_coluna].notnull()]
                df_falha = df[df[nome_nova_coluna].isnull()]

            # Passo 3: Resultados e Download
            st.divider()
            st.subheader("2. Resultado da Extração")
            
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"✅ Padrões encontrados: {len(df_sucesso)}")
                st.dataframe(df_sucesso[[coluna_alvo, nome_nova_coluna]].head())
            
            with col2:
                st.warning(f"⚠️ Padrão não encontrado: {len(df_falha)}")
                if not df_falha.empty:
                    st.dataframe(df_falha[[coluna_alvo]].head())

            # Botão de Download
            excel_data = converter_df_para_excel(df)
            
            st.download_button(
                label="📥 Baixar Planilha Organizada (.xlsx)",
                data=excel_data,
                file_name="relatorio_falhas_limpo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")