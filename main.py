import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Orquestrador CSV - Debug + Export", layout="wide")


# -------------------------
# Util: detectar encoding (tenta várias) e separador
# -------------------------
def detectar_encoding_sem_chardet(uploaded_file):
    encs = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
    raw = uploaded_file.read(8192)
    for enc in encs:
        try:
            raw.decode(enc)
            uploaded_file.seek(0)
            return enc
        except Exception:
            continue
    uploaded_file.seek(0)
    return "latin-1"


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
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


# -------------------------
# Ler e filtrar arquivos (normaliza col names)
# -------------------------
@st.cache_data
def carregar_e_filtrar(arquivos, lotacoes_selecionadas):
    dfs = []
    diagnostics = []  # guardará info sobre cada arquivo lido
    for up in arquivos:
        nome = up.name
        try:
            enc = detectar_encoding_sem_chardet(up)
            sep = detectar_separador(up, enc)
            up.seek(0)
            df = pd.read_csv(up, sep=sep, encoding=enc, engine="python")
        except Exception as e:
            diagnostics.append({"file": nome, "status": "erro_read", "msg": str(e)})
            continue

        # Normalizar nomes de colunas: strip e lower, e manter mapeamento
        col_map = {c: c.strip() for c in df.columns}
        df.rename(columns=col_map, inplace=True)
        df.columns = [c.strip() for c in df.columns]
        # keep original columns but also create lowercase versions for flexible access
        df.columns = [c for c in df.columns]
        df_lc = df.rename(columns={c: c.lower() for c in df.columns})

        # Verificações básicas
        if "lotacao" not in df_lc.columns:
            diagnostics.append({"file": nome, "status": "no_lotacao", "columns": list(df.columns)})
            continue

        # filtragem por lotacao - procura valores exatos em coluna original (não lowercased content)
        # forma robusta: transformar valores da coluna em string e strip
        df["Lotacao_tmp_for_filter"] = df_lc["lotacao"].astype(str).str.strip()
        prev_len = len(df)
        df = df[df["Lotacao_tmp_for_filter"].isin(lotacoes_selecionadas)]
        after_len = len(df)

        diagnostics.append({
            "file": nome,
            "status": "ok",
            "encoding": enc,
            "sep": sep,
            "rows_before": prev_len,
            "rows_after": after_len,
            "columns": list(df.columns)
        })

        if after_len == 0:
            # mesmo que não tenha registros após filtro, registramos e continuamos
            continue

        # restaurar colunas (remover auxiliar)
        df.drop(columns=["Lotacao_tmp_for_filter"], inplace=True, errors="ignore")

        dfs.append(df)

    if not dfs:
        return pd.DataFrame(), diagnostics
    return pd.concat(dfs, ignore_index=True, sort=False), diagnostics


# -------------------------
# Normaliza nomes de coluna para uso consistente
# -------------------------
def normalize_columns(df):
    # Cria mapa lower->original quando possível
    mapping = {}
    for c in df.columns:
        mapping[c.lower().strip()] = c
    return mapping


# -------------------------
# Cria grupos sem sobreposição
# -------------------------
def criar_grupos(df):
    df = df.copy()
    # normalize mapping
    map_cols = normalize_columns(df)

    # nomes usados
    col_mg_disp = map_cols.get("mg_emprestimo_disponivel", map_cols.get("mg_emprestimo_disponivel".lower()))
    col_mg_total = map_cols.get("mg_emprestimo_total", map_cols.get("mg_emprestimo_total".lower()))
    col_cpf = map_cols.get("cpf", map_cols.get("cpf"))

    # se colunas essenciais não existirem, retornamos dict vazio e mensagem
    missing = []
    if col_mg_disp is None and "MG_Emprestimo_Disponivel" not in df.columns:
        missing.append("MG_Emprestimo_Disponivel")
    if col_mg_total is None and "MG_Emprestimo_Total" not in df.columns:
        missing.append("MG_Emprestimo_Total")
    if col_cpf is None and "CPF" not in df.columns:
        missing.append("CPF")

    if missing:
        raise ValueError(f"Colunas faltando: {missing}. Colunas encontradas: {list(df.columns)}")

    # usar nomes reais das colunas
    disp = col_mg_disp if col_mg_disp in df.columns else "MG_Emprestimo_Disponivel"
    total = col_mg_total if col_mg_total in df.columns else "MG_Emprestimo_Total"
    cpfcol = col_cpf if col_cpf in df.columns else "CPF"

    # garantir tipos numéricos
    df[disp] = pd.to_numeric(df[disp], errors="coerce")
    df[total] = pd.to_numeric(df[total], errors="coerce")
    # garantir cpf como string
    df[cpfcol] = df[cpfcol].astype(str).str.strip()

    cpfs_class = set()
    grupos = {}

    # negativos (<0)
    g_neg = df[df[disp] < 0].copy()
    g_neg = g_neg[~g_neg[cpfcol].isin(cpfs_class)]
    cpfs_class.update(g_neg[cpfcol].dropna().unique().tolist())
    grupos["negativos"] = g_neg

    # menor50 (<50, >=0)
    g_m50 = df[(df[disp] < 50) & (df[disp] >= 0) & ~df[cpfcol].isin(cpfs_class)].copy()
    cpfs_class.update(g_m50[cpfcol].dropna().unique().tolist())
    grupos["menor50"] = g_m50

    # supertomador: ratio < 0.30, disp >=50
    cond = (df[total] > 0) & ((df[disp] / df[total]) < 0.30) & (df[disp] >= 50) & ~df[cpfcol].isin(cpfs_class)
    g_super = df[cond].copy()
    cpfs_class.update(g_super[cpfcol].dropna().unique().tolist())
    grupos["supertomador"] = g_super

    # tomador: ratio < 0.60, disp >=50, e não super
    cond2 = (df[total] > 0) & ((df[disp] / df[total]) < 0.60) & (df[disp] >= 50) & ~df[cpfcol].isin(cpfs_class)
    g_tom = df[cond2].copy()
    cpfs_class.update(g_tom[cpfcol].dropna().unique().tolist())
    grupos["tomador"] = g_tom

    # resto
    g_resto = df[~df[cpfcol].isin(cpfs_class)].copy()
    grupos["resto"] = g_resto

    return grupos, cpfcol


# -------------------------
# Ajusta colunas de saída: Apenas CPF / CPF+Matricula / Todas
# -------------------------
def ajustar_colunas(df, tipo, cpfcol):
    df = df.copy()
    # normalizar nomes baixos
    cols_lower = {c.lower(): c for c in df.columns}
    if tipo == "Apenas CPF":
        if cpfcol in df.columns:
            out = df[[cpfcol]].drop_duplicates().rename(columns={cpfcol: "CPF"}).reset_index(drop=True)
        else:
            out = pd.DataFrame(columns=["CPF"])
    elif tipo == "CPF e Matrícula":
        matricula_col = cols_lower.get("matricula")
        cols = []
        if cpfcol in df.columns:
            cols.append(cpfcol)
        if matricula_col:
            cols.append(matricula_col)
        if not cols:
            out = pd.DataFrame(columns=["CPF", "Matricula"])
        else:
            out = df[cols].drop_duplicates()
            # rename to standard
            rename_map = {}
            if cpfcol in out.columns:
                rename_map[cpfcol] = "CPF"
            if matricula_col in out.columns:
                rename_map[matricula_col] = "Matricula"
            out = out.rename(columns=rename_map).reset_index(drop=True)
    else:
        out = df.drop_duplicates().reset_index(drop=True)
    return out


# -------------------------
# Dividir em partes e criar bytes
# -------------------------
def dividir_em_partes(df, limite=50000):
    partes = []
    n = len(df)
    if n == 0:
        return partes
    num = (n // limite) + (1 if n % limite else 0)
    for i in range(num):
        ini = i * limite
        fim = ini + limite
        partes.append(df.iloc[ini:fim].reset_index(drop=True))
    return partes


def df_to_bytes(df, sep=","):
    buf = BytesIO()
    df.to_csv(buf, index=False, sep=sep)
    buf.seek(0)
    return buf.read()


# -------------------------
# UI
# -------------------------
st.title("Orquestrador CSV — Debug & Export")

st.markdown("""
Faça upload de CSV(s). O app vai:
- detectar encoding/separador,
- filtrar por Lotação(s),
- criar 5 grupos (negativos, menor50, supertomador, tomador, resto) sem sobreposição,
- permitir escolher tipo de saída (Apenas CPF / CPF+Matricula / Todas colunas),
- dividir grupos em partes de 50k se necessário,
- mostrar diagnóstico para cada arquivo lido.
""")

uploaded = st.file_uploader("Selecione um ou mais CSV", accept_multiple_files=True, type=["csv", "txt"])
lot_input = st.text_input("Lotações (separadas por vírgula)", placeholder="EX: FINANCEIRO, RH, DIRETORIA")
tipo_saida = st.selectbox("Tipo de saída:", ["Apenas CPF", "CPF e Matrícula", "Todas as colunas"])
processar = st.button("Processar")

if processar:
    if not uploaded:
        st.error("Nenhum arquivo enviado.")
    elif not lot_input.strip():
        st.error("Informe ao menos uma lotação.")
    else:
        lotacoes = [x.strip() for x in lot_input.split(",") if x.strip()]
        base, diagnostics = carregar_e_filtrar(uploaded, lotacoes)

        st.write("### Diagnóstico de arquivos carregados")
        for d in diagnostics:
            st.write(d)

        if base.empty:
            st.error("Nenhum registro após leitura e filtro por lotações. Verifique diagnóstico acima.")
        else:
            st.write("### Preview (primeiras linhas)")
            st.dataframe(base.head())

            try:
                grupos, cpfcol = criar_grupos(base)
            except Exception as e:
                st.error(f"Erro ao criar grupos: {e}")
                st.stop()

            # mostrar contagens por grupo
            cont = {k: len(v) for k, v in grupos.items()}
            st.write("### Contagens por grupo")
            st.json(cont)

            st.markdown("---")
            st.write("### Downloads gerados")

            convenio = "CONVENIO"
            if "Convenio" in base.columns:
                try:
                    convenio = str(base["Convenio"].dropna().iloc[0])
                except Exception:
                    convenio = "CONVENIO"

            any_generated = False
            for nome, g in grupos.items():
                # remover CPFs vazios
                if cpfcol in g.columns:
                    g = g[g[cpfcol].notna() & (g[cpfcol].astype(str).str.strip() != "")]
                # ajustar colunas
                out = ajustar_colunas(g, tipo_saida, cpfcol)
                if out.empty:
                    st.write(f"**{nome}** — nenhum registro após ajustes.")
                    continue

                partes = dividir_em_partes(out, limite=50000)
                st.write(f"**{nome}** — {len(out):,} registros — {len(partes)} arquivo(s)")

                for idx, parte in enumerate(partes, start=1):
                    filename = f"{convenio} - {nome}.csv" if len(partes) == 1 else f"{convenio} - {nome}_parte{idx}.csv"
                    csv_bytes = df_to_bytes(parte, sep=",")

                    st.download_button(
                        label=f"⬇️ Baixar {filename}",
                        data=csv_bytes,
                        file_name=filename,
                        mime="text/csv"
                    )
                    any_generated = True

            if not any_generated:
                st.warning("Nenhum arquivo foi gerado — verifique se as colunas e filtros estão corretos.")
            else:
                st.success("Arquivos prontos para download.")
