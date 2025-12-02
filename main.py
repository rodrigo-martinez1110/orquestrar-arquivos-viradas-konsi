import streamlit as st
import pandas as pd
import chardet

st.set_page_config(page_title="Leitor Inteligente de CSV", layout="wide")


# -----------------------------------------------
# Função: Detectar encoding automaticamente
# -----------------------------------------------
def detectar_encoding(arquivo):
    conteudo = arquivo.read()
    arquivo.seek(0)

    detect = chardet.detect(conteudo)
    encoding = detect["encoding"] or "utf-8"

    # Normalizar para Latin-1 caso detectado
    if encoding.lower() in ["iso-8859-1", "latin-1", "latin1", "cp1252"]:
        return "latin-1"

    return "utf-8"


# -----------------------------------------------
# Função: Detectar delimitador automaticamente
# -----------------------------------------------
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

    # retorna o delimitador mais frequente
    return max(contagem, key=contagem.get)


# -----------------------------------------------
# Função: Carregar 1 ou mais arquivos CSV
# -----------------------------------------------
@st.cache_data
def carregar_arquivos(arquivos):
    lista = []

    for arquivo in arquivos:

        # Detectar encoding
        encoding = detectar_encoding(arquivo)

        # Detectar separador
        separador = detectar_separador(arquivo, encoding)

        try:
            arquivo.seek(0)
            df = pd.read_csv(
                arquivo,
                sep=separador,
                encoding=encoding,
                engine="python",
                low_memory=False
            )

            st.success(f"✔ {arquivo.name} carregado | sep='{separador}' | enc='{encoding}'")
            lista.append(df)

        except Exception as e:
            st.error(f"Erro ao ler {arquivo.name}: {e}")
            continue

    if len(lista) == 0:
        return pd.DataFrame()

    return pd.concat(lista, ignore_index=True)


# -----------------------------------------------
# UI do app
# -----------------------------------------------
st.title("📂 Leitor Inteligente de Arquivos CSV")

st.write("Este app detecta automaticamente **separador** e **encoding (UTF-8 ou Latin-1)**.")

arquivos = st.file_uploader(
    "Selecione um ou mais arquivos CSV",
    type=["csv", "txt"],
    accept_multiple_files=True
)

if arquivos:
    df_final = carregar_arquivos(arquivos)

    st.subheader("📊 Dados Carregados")

    st.dataframe(df_final)

    st.write(f"**Total de linhas:** {len(df_final):,}")
