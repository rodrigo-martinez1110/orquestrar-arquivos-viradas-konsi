import pandas as pd
import streamlit as st

# Configurações iniciais
st.set_page_config(page_title="Processador de Arquivos", layout="wide")

# Função para carregar arquivos com detecção automática de delimitador
@st.cache_data
def carregar_arquivos(arquivos):
    lista = []

    for arquivo in arquivos:
        try:
            base = pd.read_csv(
                arquivo,
                sep=None,              # Detecta delimitador automaticamente
                engine="python",       # Obrigatório para sep=None
                low_memory=False,
                encoding="utf-8"
            )
        except Exception as e:
            print(f"Erro ao carregar {arquivo}: {e}")
            return None

        print(f"Arquivo carregado: {arquivo}, Linhas: {len(base)}, Colunas: {len(base.columns)}")
        lista.append(base)

    if lista:
        base_final = pd.concat(lista, ignore_index=True, join='outer')
        print(f"DataFrame final criado com {len(base_final)} linhas e {len(base_final.columns)} colunas.")
        return base_final
    else:
        print("Nenhum arquivo foi carregado com sucesso.")
        return None


# Função para dividir DataFrames em partes menores (50k)
def dividir_em_partes(df, limite=50000):
    partes = []
    total_linhas = len(df)

    if total_linhas <= limite:
        return [df]

    num_partes = (total_linhas // limite) + (1 if total_linhas % limite > 0 else 0)

    for i in range(num_partes):
        inicio = i * limite
        fim = inicio + limite
        partes.append(df.iloc[inicio:fim])

    return partes


# Função para gerar os arquivos filtrados
def gerar_arquivos_filtrados(base, tipo_planilha):
    colunas_iguais = base['MG_Emprestimo_Disponivel'].equals(base['MG_Emprestimo_Total'])
    cpfs_classificados = set()

    if colunas_iguais:
        negativos = base[base['MG_Emprestimo_Disponivel'] < 0]
        cpfs_classificados.update(negativos['CPF'].tolist())

        menores_50 = base[
            (base['MG_Emprestimo_Disponivel'] < 50) &
            ~base['CPF'].isin(cpfs_classificados)
        ]
        cpfs_classificados.update(menores_50['CPF'].tolist())

        menores_300 = base[
            (base['MG_Emprestimo_Disponivel'] < 300) &
            (base['MG_Emprestimo_Disponivel'] >= 50) &
            ~base['CPF'].isin(cpfs_classificados)
        ]
        cpfs_classificados.update(menores_300['CPF'].tolist())

        menores_500 = base[
            (base['MG_Emprestimo_Disponivel'] < 500) &
            (base['MG_Emprestimo_Disponivel'] >= 300) &
            ~base['CPF'].isin(cpfs_classificados)
        ]
        cpfs_classificados.update(menores_500['CPF'].tolist())

        restante = base[
            (base['MG_Emprestimo_Disponivel'] >= 500) &
            ~base['CPF'].isin(cpfs_classificados)
        ]

        super_tomador = None
        tomador = None

    else:
        negativos = base[base['MG_Emprestimo_Disponivel'] < 0]
        cpfs_classificados.update(negativos['CPF'].tolist())

        menores_50 = base[
            (base['MG_Emprestimo_Disponivel'] < 50) &
            ~base['CPF'].isin(cpfs_classificados)
        ]
        cpfs_classificados.update(menores_50['CPF'].tolist())

        super_tomador = base[
            (base['MG_Emprestimo_Disponivel'] / base['MG_Emprestimo_Total'] < 0.35) &
            (base['MG_Emprestimo_Disponivel'] >= 50) &
            ~base['CPF'].isin(cpfs_classificados)
        ]
        cpfs_classificados.update(super_tomador['CPF'].tolist())

        tomador = base[
            (base['MG_Emprestimo_Disponivel'] != base['MG_Emprestimo_Total']) &
            ~base['CPF'].isin(cpfs_classificados)
        ]

        restante = base[
            ~base['CPF'].isin(cpfs_classificados)
        ]

        menores_300 = None
        menores_500 = None

    arquivos = {
        "negativos": negativos,
        "menores_50": menores_50,
        "super_tomador": super_tomador,
        "menores_300": menores_300,
        "menores_500": menores_500,
        "tomador": tomador,
        "restante": restante
    }

    for key, dataframe in arquivos.items():
        if dataframe is not None:
            if tipo_planilha == "Molde CPF":
                arquivos[key] = dataframe[['CPF']].rename(columns={'CPF': 'cpf'})

            elif tipo_planilha == "Molde CPF e Matrícula":
                arquivos[key] = dataframe[['CPF', 'Matricula']].rename(columns={'CPF': 'cpf', 'Matricula': 'matricula'})
                arquivos[key]['senha'] = ''
                arquivos[key]['nome'] = ''
                arquivos[key] = arquivos[key][['cpf', 'senha', 'matricula', 'nome']]

    return arquivos


# Interface do Streamlit
st.title("Processador de Arquivos CSV")

st.sidebar.title("Configurações")
arquivos = st.sidebar.file_uploader("Arraste e solte seus arquivos CSV aqui", accept_multiple_files=True, type=['csv'])
st.sidebar.write("---")

tipo_planilha = st.sidebar.radio("Selecione o tipo de planilha que deseja retornar:", ["Molde CPF", "Molde CPF e Matrícula"])

if arquivos:
    base = carregar_arquivos(arquivos)

    st.write("### Pré-visualização dos dados carregados")
    st.dataframe(base.head())
    st.write(base.shape)
    st.write("---")

    base = base.sort_values(by='MG_Emprestimo_Disponivel', ascending=True)
    base = base.drop_duplicates(subset='CPF')
    base = base.reset_index(drop=True)

    arquivos_filtrados = gerar_arquivos_filtrados(base, tipo_planilha)
    convenio = base.loc[1, 'Convenio']

    st.write(f"### Arquivos Gerados para Download - {convenio.upper()}")

    for nome, df in arquivos_filtrados.items():
        if df is not None:

            partes = dividir_em_partes(df, limite=50000)

            if len(partes) == 1:
                csv = partes[0].to_csv(index=False, sep=",")
                st.download_button(
                    label=f"Baixar {nome}.csv",
                    data=csv,
                    file_name=f"{convenio} - {nome}.csv",
                    mime="text/csv"
                )
            else:
                for idx, parte in enumerate(partes, start=1):
                    csv = parte.to_csv(index=False, sep=",")
                    st.download_button(
                        label=f"Baixar {nome}_parte{idx}.csv",
                        data=csv,
                        file_name=f"{convenio} - {nome}_parte{idx}.csv",
                        mime="text/csv"
                    )

                st.info(f"O grupo **{nome}** foi dividido em **{len(partes)} partes**, pois ultrapassou 50.000 registros.")
