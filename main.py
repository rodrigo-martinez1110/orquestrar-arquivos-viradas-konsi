import streamlit as st
import pandas as pd


# -------------------------------------------------------------------
# Detectar encoding sem chardet
# -------------------------------------------------------------------
def detectar_encoding_sem_chardet(arquivo):
    for enc in ["utf-8", "latin-1", "iso-8859-1"]:
        try:
            arquivo.seek(0)
            arquivo.read().decode(enc)
            return enc
        except:
            pass
    return "latin-1"


# -------------------------------------------------------------------
# Detectar separador automático
# -------------------------------------------------------------------
def detectar_separador(arquivo, encoding):
    arquivo.seek(0)
    try:
        linhas = arquivo.read().decode(encoding).split("\n")[:5]
    except:
        return ","

    arquivo.seek(0)

    amostra = "\n".join(linhas)
    delimitadores = [",", ";", "|", "\t"]

    contagem = {d: amostra.count(d) for d in delimitadores}
    return max(contagem, key=contagem.get)


# -------------------------------------------------------------------
# Carregar E filtrar antes de juntar
# -------------------------------------------------------------------
@st.cache_data
def carregar_e_filtrar(arquivos, lotacoes_selecionadas):

    lista = []

    for arquivo in arquivos:
        nome = arquivo.name

        # Detectar encoding
        encoding = detectar_encoding_sem_chardet(arquivo)

        # Detectar separador
        separador = detectar_separador(arquivo, encoding)

        try:
            arquivo.seek(0)
            df = pd.read_csv(
                arquivo,
                sep=separador,
                encoding=encoding,
                engine="python"   # remove low_memory
            )
        except Exception as e:
            st.error(f"Erro ao ler {nome}: {e}")
            continue

        # Validar coluna Lotacao
        if "Lotacao" not in df.columns:
            st.error(f"O arquivo {nome} não possui a coluna 'Lotacao'.")
            continue

        # Filtrar lotações desejadas
        df = df[df["Lotacao"].isin(lotacoes_selecionadas)]

        lista.append(df)

    if not lista:
        return pd.DataFrame()

    # Juntar tudo já filtrado
    return pd.concat(lista, ignore_index=True)


# -------------------------------------------------------------------
# Dividir em arquivos de 50.000 linhas
# -------------------------------------------------------------------
def gerar_arquivos_50k(df):
    arquivos = []
    total = len(df)
    partes = total // 50000 + (1 if total % 50000 else 0)

    for i in range(partes):
        chunk = df.iloc[i * 50000:(i + 1) * 50000]
        nome = f"saida_parte_{i+1}.csv"
        chunk.to_csv(nome, index=False, sep=";")
        arquivos.append(nome)

    return arquivos


# -------------------------------------------------------------------
# Interface Streamlit
# -------------------------------------------------------------------
st.title("📂 Filtrador + Unificador de CSV com Lotações")

arquivos = st.file_uploader(
    "Selecione arquivos CSV",
    type=["csv", "txt"],
    accept_multiple_files=True
)

lotacoes_input = st.text_input(
    "Informe as Lotações desejadas, separadas por vírgula:",
    placeholder="Ex: FINANCEIRO, RH, DIRETORIA"
)

if arquivos and lotacoes_input.strip():

    lotacoes_selecionadas = [x.strip() for x in lotacoes_input.split(",")]

    st.info(f"Filtrando pelas Lotações: {lotacoes_selecionadas}")

    df_final = carregar_e_filtrar(arquivos, lotacoes_selecionadas)

    st.subheader("📊 Dados filtrados")
    st.dataframe(df_final)

    if not df_final.empty:
        arquivos_gerados = gerar_arquivos_50k(df_final)

        st.success(f"{len(arquivos_gerados)} arquivos gerados com sucesso!")

        for arq in arquivos_gerados:
            with open(arq, "rb") as f:
                st.download_button(
                    "⬇️ Baixar " + arq,
                    data=f,
                    file_name=arq,
                    mime="text/csv"
                )
