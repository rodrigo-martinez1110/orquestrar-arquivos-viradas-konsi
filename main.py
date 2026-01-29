import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Orquestrador CSV", layout="wide")

# =========================================================
# Detectar encoding (sem reler arquivo várias vezes)
# =========================================================
def detectar_encoding(raw: bytes):
    encs = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
    for e in encs:
        try:
            raw.decode(e)
            return e
        except:
            pass
    return "latin-1"


# =========================================================
# Detectar separador
# =========================================================
def detectar_separador(raw: bytes, encoding: str):
    try:
        sample = raw[:4096].decode(encoding, errors="ignore")
    except:
        return ","

    candidates = [",", ";", "|", "\t"]
    counts = {c: sample.count(c) for c in candidates}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


# =========================================================
# Carregar e filtrar CSVs (OTIMIZADO)
# =========================================================
def carregar_e_filtrar(arquivos, lotacoes):
    dfs = []
    diagn = []

    cols_minimas = [
        "cpf",
        "lotacao",
        "mg_emprestimo_disponivel",
        "mg_emprestimo_total",
        "senha",
        "matricula",
        "nome",
    ]

    for up in arquivos:
        nome = up.name
        try:
            raw = up.read()  # 🔹 leitura única
            enc = detectar_encoding(raw)
            sep = detectar_separador(raw, enc)

            bio = BytesIO(raw)

            # tenta engine C primeiro
            try:
                df = pd.read_csv(
                    bio,
                    sep=sep,
                    encoding=enc,
                    low_memory=False
                )
            except Exception:
                bio.seek(0)
                df = pd.read_csv(
                    bio,
                    sep=sep,
                    encoding=enc,
                    engine="python",
                    low_memory=False
                )

            # padroniza colunas
            df.columns = [c.strip().lower() for c in df.columns]

            if "lotacao" not in df.columns:
                diagn.append({"file": nome, "status": "sem coluna lotacao"})
                continue

            before = len(df)

            # mantém só colunas necessárias
            df = df[[c for c in cols_minimas if c in df.columns]]

            # tipos leves
            df["cpf"] = df["cpf"].astype("string").str.strip()
            df["lotacao"] = df["lotacao"].astype("string").str.strip()

            if "mg_emprestimo_disponivel" in df.columns:
                df["mg_emprestimo_disponivel"] = pd.to_numeric(
                    df["mg_emprestimo_disponivel"],
                    errors="coerce",
                    downcast="float"
                )

            if "mg_emprestimo_total" in df.columns:
                df["mg_emprestimo_total"] = pd.to_numeric(
                    df["mg_emprestimo_total"],
                    errors="coerce",
                    downcast="float"
                )

            # filtra lotação apenas se informado
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


# =========================================================
# Criar grupos
# =========================================================
def criar_grupos(df):
    req = ["cpf", "mg_emprestimo_disponivel", "mg_emprestimo_total"]
    for r in req:
        if r not in df.columns:
            raise ValueError(f"Coluna obrigatória faltando: {r}")

    usados = set()
    grupos = {}

    g = df[df["mg_emprestimo_disponivel"] < 0]
    usados.update(g["cpf"])
    grupos["negativos"] = g

    g = df[
        (df["mg_emprestimo_disponivel"] < 50) &
        (df["mg_emprestimo_disponivel"] >= 0) &
        (~df["cpf"].isin(usados))
    ]
    usados.update(g["cpf"])
    grupos["menor50"] = g

    g = df[
        (df["mg_emprestimo_total"] > 0) &
        ((df["mg_emprestimo_disponivel"] / df["mg_emprestimo_total"]) < 0.30) &
        (df["mg_emprestimo_disponivel"] >= 50) &
        (~df["cpf"].isin(usados))
    ]
    usados.update(g["cpf"])
    grupos["supertomador"] = g

    g = df[
        (df["mg_emprestimo_total"] > 0) &
        ((df["mg_emprestimo_disponivel"] / df["mg_emprestimo_total"]) < 0.60) &
        (df["mg_emprestimo_disponivel"] >= 50) &
        (~df["cpf"].isin(usados))
    ]
    usados.update(g["cpf"])
    grupos["tomador"] = g

    grupos["resto"] = df[~df["cpf"].isin(usados)]

    return grupos


# =========================================================
# Ajustar colunas
# =========================================================
def ajustar_colunas(df, tipo):
    if tipo == "Apenas CPF":
        return df[["cpf"]].drop_duplicates()

    elif tipo == "CPF e Matrícula":
        cols = ["cpf", "senha", "matricula", "nome"]
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols].drop_duplicates()

    return df.drop_duplicates()


# =========================================================
# Dividir DataFrame
# =========================================================
def split_df(df, limit=50000):
    return [
        df.iloc[i:i + limit].reset_index(drop=True)
        for i in range(0, len(df), limit)
    ]


def df_to_bytes(df):
    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf.read()


# =========================================================
# UI
# =========================================================
st.title("Orquestrador CSV – Versão Otimizada (CSV Pesado)")

uploaded = st.file_uploader(
    "Envie um ou mais CSV",
    accept_multiple_files=True
)

lot = st.text_input("Lotações (separadas por vírgula) — opcional")

tipo = st.selectbox(
    "Tipo de saída:",
    ["Apenas CPF", "CPF e Matrícula", "Todas as colunas"]
)

if uploaded:
    lotacoes = [x.strip() for x in lot.split(",") if x.strip()]

    base, diag = carregar_e_filtrar(uploaded, lotacoes)

    st.subheader("Diagnóstico")
    st.table(pd.DataFrame(diag))

    if base.empty:
        st.error("Nenhuma linha após filtragem.")
        st.stop()

    st.subheader("Preview (20 linhas)")
    st.table(base.head(20))

    grupos = criar_grupos(base)

    st.subheader("Quantidade por grupo")
    st.json({k: len(v) for k, v in grupos.items()})

    st.divider()
    st.subheader("Downloads")

    for nome, g in grupos.items():
        out = ajustar_colunas(g, tipo)

        if out.empty:
            st.write(f"{nome}: vazio")
            continue

        partes = split_df(out, 50000)

        for i, parte in enumerate(partes, 1):
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
