import streamlit as st
import pandas as pd


# -------------------------------------
# Detectar encoding sem chardet
# -------------------------------------
def detectar_encoding_sem_chardet(arquivo):
    for enc in ["utf-8", "latin-1", "iso-8859-1"]:
        try:
            arquivo.seek(0)
            arquivo.read().decode(enc)
            return enc
        except:
            pass
    return "latin-1"


# -------------------------------------
# Detectar separador automaticamente
# -------------------------------------
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


# -------------------------------------
# Carregar e filtrar por Lotação
# -------------------------------------
@st.cache_data
def carregar_e_filtrar(arquivos, lotacoes):
    lista = []

    for arquivo in arquivos:
        nome = arquivo.name

        encoding = detectar_encoding_sem_chardet(arquivo)
        separador = detectar_separador(arquivo, encoding)

        try:
            arquivo.seek(0)
            df = pd.read_csv(
                arquivo,
                sep=separador,
                encoding=encoding,
                engine="python"
            )
        except Exception as e:
            st.error(f"Erro ao ler {nome}: {e}")
            continue

        # Garantir que tem Lotacao
        if "Lotacao" not in df.columns:
            st.error(f"O arquivo {nome} não possui a coluna 'Lotacao'.")
            continue

        # Garantir colunas de margem
        if "MG_Emprestimo_Disponivel" not in df.columns:
            st.error(f"O arquivo {nome} não possui MG_Emprestimo_Disponivel.")
            continue

        if "MG_Emprestimo_Total" not in df.columns:
            st.error(f"O arquivo {nome} não possui MG_Emprestimo_Total.")
            continue

        # Filtrar as lotações desejadas
        df = df[df["Lotacao"].isin(lotacoes)]

        lista.append(df)

    if not lista:
        return pd.DataFrame()

    return pd.concat(lista, ignore_index=True)


# -------------------------------------
# Função para dividir em partes de 50k
# -------------------------------------
def dividir_em_partes(df, limite=50000):
    partes = []
    total = len(df)

    if total == 0:
        return partes

    num_partes = (total // limite) + (1 if total % limite > 0 else 0)

    for i in range(num_partes):
        inicio = i * limite
        fim = inicio + limite
        partes.append(df.iloc[inicio:fim])

    return partes


# -------------------------------------
# Criar os 5 grupos e gerar arquivos
# -------------------------------------
def gerar_grupos(df):
    df["MG_Emprestimo_Disponivel"] = pd.to_numeric(df["MG_Emprestimo_Disponivel"], errors="coerce")
    df["MG_Emprestimo_Total"] = pd.to_numeric(df["MG_Emprestimo_Total"], errors="coerce")

    # Grupos:
    negativos = df[df["MG_Emprestimo_Disponivel"] < 0]

    menor50 = df[
        (df["MG_Emprestimo_Disponivel"] < 50) &
        (df["MG_Emprestimo_Disponivel"] >= 0)
    ]

    supertomador = df[
        (df["MG_Emprestimo_Disponivel"] / df["MG_Emprestimo_Total"] < 0.30) &
        (df["MG_Emprestimo_Disponivel"] >= 50)
    ]

    tomador = df[
        (df["MG_Emprestimo_Disponivel"] / df["MG_Emprestimo_Total"] < 0.60) &
        (df["MG_Emprestimo_Disponivel"] >= 50) &
        ~(df["MG_Emprestimo_Disponivel"] / df["MG_Emprestimo_Total"] < 0.30)
    ]

    usados = pd.concat([negativos, menor50, supertomador, tomador])["CPF"].unique()
    resto = df[~df["CPF"].isin(usados)]

    grupos = {
        "negativos": negativos,
        "menor50": menor50,
        "supertomador": supertomador,
        "tomador": tomador,
        "resto": resto
    }

    return grupos


# -------------------------------------
# Interface Streamlit
# -------------------------------------
st.title("📂 Processador CSV — Grupos + Arquivos de 50k")

arquivos = st.file_uploader("Selecione os arquivos CSV", type=["csv", "txt"], accept_multiple_files=True)

lot = st.text_input("Lotações desejadas (separadas por vírgula): ", placeholder="RH, FINANCEIRO, DIRETORIA")

if arquivos and lot.strip():

    lotacoes = [x.strip() for x in lot.split(",")]

    st.info(f"Filtrando pelas lotações: {lotacoes}")

    df = carregar_e_filtrar(arquivos, lotacoes)

    st.subheader("Prévia dos dados filtrados:")
    st.dataframe(df)

    if not df.empty:

        grupos = gerar_grupos(df)

        st.success("Grupos gerados! Agora você pode baixar:")

        for nome, grupo in grupos.items():
            st.write(f"### Grupo: {nome} ({len(grupo)} registros)")

            partes = dividir_em_partes(grupo)

            if not partes:
                st.write("Nenhum registro neste grupo.")
                continue

            for i, parte in enumerate(partes, start=1):
                arquivo_nome = f"{nome}.csv" if len(partes) == 1 else f"{nome}_parte{i}.csv"
                csv = parte.to_csv(index=False, sep=";").encode("utf-8")

                st.download_button(
                    label=f"⬇️ Baixar {arquivo_nome}",
                    data=csv,
                    file_name=arquivo_nome,
                    mime="text/csv"
                )
