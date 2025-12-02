import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Orquestrador CSV - Filtrar Lotações e Gerar Grupos", layout="wide")


# -------------------------
# Utils: detectar encoding
# -------------------------
def detectar_encoding_sem_chardet(uploaded_file):
    # tenta decodificar o começo do arquivo com encodings comuns
    encs = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
    raw = uploaded_file.read(4096)  # lê um pedaço
    for enc in encs:
        try:
            raw.decode(enc)
            uploaded_file.seek(0)
            return enc
        except Exception:
            continue
    uploaded_file.seek(0)
    return "latin-1"


# -------------------------
# Utils: detectar separador
# -------------------------
def detectar_separador(uploaded_file, encoding):
    uploaded_file.seek(0)
    try:
        sample = uploaded_file.read(8192).decode(encoding, errors="replace")
    except Exception:
        uploaded_file.seek(0)
        return ","
    uploaded_file.seek(0)

    candidates = [",", ";", "|", "\t"]
    counts = {c: sample.count(c) for c in candidates}
    # se todos zero, fallback ","
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


# -------------------------
# Carregar vários arquivos (detecta encoding/separador) e filtra Lotacao
# -------------------------
@st.cache_data
def carregar_e_filtrar(arquivos, lotacoes_selecionadas):
    dfs = []
    for up in arquivos:
        nome = up.name
        try:
            enc = detectar_encoding_sem_chardet(up)
            sep = detectar_separador(up, enc)
            up.seek(0)
            df = pd.read_csv(up, sep=sep, encoding=enc, engine="python")
        except Exception as e:
            # registra erro, mas continua com os outros arquivos
            st.warning(f"Falha ao ler '{nome}': {e}")
            continue

        # verificar colunas obrigatórias
        if "Lotacao" not in df.columns:
            st.warning(f"O arquivo '{nome}' não contém a coluna 'Lotacao'. Será ignorado.")
            continue

        # filtrar por lotação
        df = df[df["Lotacao"].isin(lotacoes_selecionadas)]

        # algumas vezes colunas podem vir com espaços, normaliza nomes comuns
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()
    # concatena tudo
    return pd.concat(dfs, ignore_index=True, sort=False)


# -------------------------
# Função para criar grupos (sem sobreposição)
# -------------------------
def criar_grupos_sem_sobreposicao(df):
    # garantir colunas numéricas
    df = df.copy()
    df["MG_Emprestimo_Disponivel"] = pd.to_numeric(df["MG_Emprestimo_Disponivel"], errors="coerce")
    df["MG_Emprestimo_Total"] = pd.to_numeric(df["MG_Emprestimo_Total"], errors="coerce")

    cpfs_classificados = set()
    grupos = {}

    # negativos: MG_Emprestimo_Disponivel < 0
    negativos = df[df["MG_Emprestimo_Disponivel"] < 0]
    grupos["negativos"] = negativos[~negativos["CPF"].isin(cpfs_classificados)]
    cpfs_classificados.update(grupos["negativos"]["CPF"].astype(str).tolist())

    # menor50: MG_Emprestimo_Disponivel < 50 (e não classificados)
    menores_50 = df[
        (df["MG_Emprestimo_Disponivel"] < 50) &
        ~df["CPF"].isin(cpfs_classificados)
    ]
    grupos["menor50"] = menores_50
    cpfs_classificados.update(menores_50["CPF"].astype(str).tolist())

    # supertomador: ratio < 0.30, MG_Emprestimo_Disponivel >= 50
    # proteger divisão por zero / NaN: considerar apenas MG_Emprestimo_Total > 0
    cond_super = (
        (df["MG_Emprestimo_Total"] > 0) &
        ((df["MG_Emprestimo_Disponivel"] / df["MG_Emprestimo_Total"]) < 0.30) &
        (df["MG_Emprestimo_Disponivel"] >= 50) &
        ~df["CPF"].isin(cpfs_classificados)
    )
    supertomador = df[cond_super]
    grupos["supertomador"] = supertomador
    cpfs_classificados.update(supertomador["CPF"].astype(str).tolist())

    # tomador: ratio < 0.60, MG_Emprestimo_Disponivel >= 50, e não supertomador
    cond_tomador = (
        (df["MG_Emprestimo_Total"] > 0) &
        ((df["MG_Emprestimo_Disponivel"] / df["MG_Emprestimo_Total"]) < 0.60) &
        (df["MG_Emprestimo_Disponivel"] >= 50) &
        ~df["CPF"].isin(cpfs_classificados)
    )
    tomador = df[cond_tomador]
    grupos["tomador"] = tomador
    cpfs_classificados.update(tomador["CPF"].astype(str).tolist())

    # resto: tudo que não foi classificado
    resto = df[~df["CPF"].isin(cpfs_classificados)]
    grupos["resto"] = resto

    return grupos


# -------------------------
# Ajustar colunas de saída conforme tipo escolhido
# -------------------------
def ajustar_colunas_para_saida(df, tipo_saida):
    if tipo_saida == "Apenas CPF":
        if "CPF" not in df.columns:
            return pd.DataFrame(columns=["CPF"])
        return df[["CPF"]].drop_duplicates().reset_index(drop=True)
    elif tipo_saida == "CPF e Matrícula":
        cols = [c for c in ["CPF", "Matricula"] if c in df.columns]
        if not cols:
            return pd.DataFrame(columns=["CPF", "Matricula"])
        return df[cols].drop_duplicates().reset_index(drop=True)
    else:  # Todas as colunas
        return df.drop_duplicates().reset_index(drop=True)


# -------------------------
# Dividir DataFrame em partes de limite linhas
# -------------------------
def dividir_em_partes(df, limite=50000):
    partes = []
    n = len(df)
    if n == 0:
        return partes
    num_partes = (n // limite) + (1 if n % limite else 0)
    for i in range(num_partes):
        ini = i * limite
        fim = ini + limite
        partes.append(df.iloc[ini:fim].reset_index(drop=True))
    return partes


# -------------------------
# Helper: converte DataFrame para bytes CSV para download
# -------------------------
def df_to_csv_bytes(df, sep=","):
    buf = BytesIO()
    df.to_csv(buf, index=False, sep=sep)
    buf.seek(0)
    return buf.read()


# -------------------------
# Streamlit UI
# -------------------------
st.title("Orquestrador CSV — Filtrar por Lotação e gerar grupos")

st.markdown(
    """
    - Faça upload de um ou mais CSVs.
    - Informe a(s) Lotação(ões) que deseja incluir (separadas por vírgula).
    - Escolha o formato de saída (Apenas CPF / CPF e Matrícula / Todas as colunas).
    - O app irá gerar 5 grupos (negativos, menor50, supertomador, tomador, resto).
    - Cada grupo será dividido em partes de até 50.000 registros se necessário.
    """
)

uploaded = st.file_uploader("Arraste ou selecione os arquivos CSV", accept_multiple_files=True, type=["csv", "txt"])
lot_input = st.text_input("Lotações desejadas (separadas por vírgula)", placeholder="EX: FINANCEIRO, RH, DIRETORIA")
tipo_saida = st.selectbox("Tipo de arquivo de saída:", ["Apenas CPF", "CPF e Matrícula", "Todas as colunas"])
botao_processar = st.button("Processar e Gerar Arquivos")

if botao_processar:
    if not uploaded:
        st.error("Envie ao menos um arquivo CSV.")
    elif not lot_input.strip():
        st.error("Informe ao menos uma Lotação.")
    else:
        lotacoes = [x.strip() for x in lot_input.split(",") if x.strip()]
        with st.spinner("Carregando e filtrando arquivos..."):
            base = carregar_e_filtrar(uploaded, lotacoes)

        if base.empty:
            st.error("Nenhum registro após filtrar pelas lotações informadas.")
        else:
            # tenta pegar um nome de convênio para usar nos nomes dos arquivos (opcional)
            convenio = "CONVENIO"
            if "Convenio" in base.columns and not base["Convenio"].isna().all():
                try:
                    convenio = str(base["Convenio"].dropna().iloc[0])
                except Exception:
                    convenio = "CONVENIO"

            st.success(f"Registros após filtro: {len(base):,} — processando grupos...")
            grupos = criar_grupos_sem_sobreposicao(base)

            #
