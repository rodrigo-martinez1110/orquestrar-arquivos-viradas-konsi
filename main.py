import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Orquestrador CSV", layout="wide")

# ---------------------------------------------------------
# Detectar encoding sem chardet
# ---------------------------------------------------------
def detectar_encoding(uploaded):
    encs = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
    raw = uploaded.read(4096)
    for e in encs:
        try:
            raw.decode(e)
            uploaded.seek(0)
            return e
        except:
            pass
    uploaded.seek(0)
    return "latin-1"


# ---------------------------------------------------------
# Detectar separador
# ---------------------------------------------------------
def detectar_separador(uploaded, encoding):
    uploaded.seek(0)
    try:
        sample = uploaded.read(4096).decode(encoding, errors="ignore")
    except:
        uploaded.seek(0)
        return ","
    uploaded.seek(0)

    candidates = [",", ";", "|", "\t"]
    counts = {c: sample.count(c) for c in candidates}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


# ---------------------------------------------------------
# Carregar e filtrar CSVs
# ---------------------------------------------------------
@st.cache_data
def carregar_e_filtrar(arquivos, lotacoes):
    dfs = []
    diagn = []

    for up in arquivos:
        nome = up.name
        try:
            enc = detectar_encoding(up)
            sep = detectar_separador(up, enc)

            up.seek(0)
            df = pd.read_csv(up, sep=sep, encoding=enc, engine="python")

            # padroniza colunas
            df.columns = [c.strip().lower() for c in df.columns]

            if "lotacao" not in df.columns:
                diagn.append({"file": nome, "status": "sem coluna lotacao"})
                continue

            before = len(df)

            df["lotacao"] = df["lotacao"].astype(str).str.strip()

            # 🔹 FILTRA APENAS SE LOTACOES FOI INFORMADO
            if lotacoes:
                df = df[df["lotacao"].isin(lotacoes)]

            after = len(df)

            diagn.append({
                "file": nome,
                "status": "ok",
                "rows_before": before,
                "rows_after": after
            })

            if after > 0:
                dfs.append(df)

        except Exception as e:
            diagn.append({"file": nome, "status": "erro", "msg": str(e)})

    if not dfs:
        return pd.DataFrame(), diagn

    return pd.concat(dfs, ignore_index=True), diagn


# ---------------------------------------------------------
# Criar grupos
# ---------------------------------------------------------
def criar_grupos(df):
    req = ["cpf", "mg_emprestimo_disponivel", "mg_emprestimo_total"]
    for r in req:
        if r not in df.columns:
            raise ValueError(f"Coluna obrigatória faltando: {r}")

    df = df.copy()

    df["mg_emprestimo_disponivel"] = pd.to_numeric(
        df["mg_emprestimo_disponivel"], errors="coerce"
    )
    df["mg_emprestimo_total"] = pd.to_numeric(
        df["mg_emprestimo_total"], errors="coerce"
    )
    df["cpf"] = df["cpf"].astype(str).str.strip()

    usados = set()
    grupos = {}

    # negativos
    g = df[df["mg_emprestimo_disponivel"] < 0].copy()
    g = g[~g["cpf"].isin(usados)]
    usados.update(g["cpf"])
    grupos["negativos"] = g

    # menor50
    g = df[
        (df["mg_emprestimo_disponivel"] < 50) &
        (df["mg_emprestimo_disponivel"] >= 0) &
        (~df["cpf"].isin(usados))
    ].copy()
    usados.update(g["cpf"])
    grupos["menor50"] = g

    # supertomador
    g = df[
        (df["mg_emprestimo_total"] > 0) &
        ((df["mg_emprestimo_disponivel"] / df["mg_emprestimo_total"]) < 0.30) &
        (df["mg_emprestimo_disponivel"] >= 50) &
        (~df["cpf"].isin(usados))
    ].copy()
    usados.update(g["cpf"])
    grupos["supertomador"] = g

    # tomador
    g = df[
        (df["mg_emprestimo_total"] > 0) &
        ((df["mg_emprestimo_disponivel"] / df["mg_emprestimo_total"]) < 0.60) &
        (df["mg_emprestimo_disponivel"] >= 50) &
        (~df["cpf"].isin(usados))
    ].copy()
    usados.update(g["cpf"])
    grupos["tomador"] = g

    # resto
    g = df[~df["cpf"].isin(usados)].copy()
    grupos["resto"] = g

    return grupos


# ---------------------------------------------------------
# Ajustar colunas conforme tipo
# ---------------------------------------------------------
def ajustar_colunas(df, tipo):
    df = df.copy()

    if tipo == "Apenas CPF":
        return df[["cpf"]].drop_duplicates().reset_index(drop=True)

    elif tipo == "CPF e Matrícula":
        colunas_final = ["cpf", "senha", "matricula", "nome"]
        for c in colunas_final:
            if c not in df.columns:
                df[c] = ""
        return df[colunas_final].drop_duplicates().reset_index(drop=True)

    else:
        return df.drop_duplicates().reset_index(drop=True)


# ---------------------------------------------------------
# Dividir em partes
# ---------------------------------------------------------
def split_df(df, limit=50000):
    parts = []
    n = len(df)
    if n == 0:
        return parts

    k = (n // limit) + (1 if n % limit else 0)
    for i in range(k):
        parts.append(
            df.iloc[i * limit:(i + 1) * limit].reset_index(drop=True)
        )
    return parts


def df_to_bytes(df):
    buf = BytesIO()
    df.to_csv(buf, index=False, sep=",")
    buf.seek(0)
    return buf.read()


# =========================================================
# UI
# =========================================================
st.title("Orquestrador CSV – Versão Melhorada")

uploaded = st.file_uploader(
    "Envie um ou mais CSV",
    accept_multiple_files=True
)

lot = st.text_input(
    "Lotações (separadas por vírgula) — opcional"
)

tipo = st.selectbox(
    "Tipo de saída:",
    ["Apenas CPF", "CPF e Matrícula", "Todas as colunas"]
)

if uploaded:

    # 🔹 se vazio, vira lista vazia e não filtra
    lotacoes = [x.strip() for x in lot.split(",") if x.strip()] if lot.strip() else []

    base, diag = carregar_e_filtrar(uploaded, lotacoes)

    st.write("### Diagnóstico resumido")
    st.dataframe(pd.DataFrame(diag))

    if base.empty:
        st.error("Nenhuma linha encontrada após filtragem.")
        st.stop()

    st.write("### Preview")
    st.dataframe(base.head())

    try:
        grupos = criar_grupos(base)
    except Exception as e:
        st.error(str(e))
        st.stop()

    st.write("### Quantidade por grupo")
    st.json({k: len(v) for k, v in grupos.items()})

    st.write("---")
    st.write("### Arquivos para download:")

    for nome, g in grupos.items():
        out = ajustar_colunas(g, tipo)

        if out.empty:
            st.write(f"{nome}: vazio")
            continue

        partes = split_df(out, 50000)

        for i, parte in enumerate(partes, start=1):
            fname = f"{nome}.csv" if len(partes) == 1 else f"{nome}_parte{i}.csv"

            st.download_button(
                f"⬇️ Baixar {fname}",
                data=df_to_bytes(parte),
                file_name=fname,
                mime="text/csv",
                key=f"{nome}_{i}"
            )

else:
    st.info("Envie arquivos para começar.")
