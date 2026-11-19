import os
from datetime import date, timedelta
from pathlib import Path


import pandas as pd
import plotly.express as px
import streamlit as st
import re


st.set_page_config(
    page_title="Controle de Gastos da Viagem",
    page_icon=":material/travel:",
    layout="wide",
)
st.markdown(
    """
    <style>
        /* Título principal */
        h1 {
            font-weight: 800 !important;
            letter-spacing: -0.02em;
        }

        /* Sidebar mais elegante */
        section[data-testid="stSidebar"] {
            background-color: #161B26;
            border-right: 1px solid #263041;
        }

        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            font-size: 0.95rem !important;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #A5B4FC !important;
        }

        /* Cartões de métricas */
        div[data-testid="stMetric"] {
            background: linear-gradient(
                145deg,
                #161B26 0%,
                #1B2230 100%
            );
            border: 1px solid #263041;
            border-radius: 0.9rem;
            padding: 1.1rem 1.25rem;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
        }

        div[data-testid="stMetricValue"] {
            color: #E6E9F0;
        }

        div[data-testid="stMetricLabel"] {
            color: #A5B4FC;
            font-weight: 600;
        }

        /* Botões */
        button[kind="primary"] {
            background-color: #6C63FF !important;
            border: none !important;
            font-weight: 600 !important;
        }

        button[kind="primary"]:hover {
            background-color: #7C74FF !important;
        }

        /* Tabelas */
        div[data-testid="stDataFrame"] {
            border: 1px solid #263041;
            border-radius: 0.75rem;
            overflow: hidden;
        }

        /* Espaçamento entre seções */
        hr {
            border-color: #263041 !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def converter_datas(serie: pd.Series) -> pd.Series:
    texto = (
        serie.astype(str)
        .str.strip()
        .str.replace("'", "", regex=False)
        .str.split(" ").str[0]
        .str.replace("/", "-", regex=False)
    )

    br = pd.to_datetime(texto, format="%d-%m-%Y", errors="coerce")
    iso = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")

    numero = pd.to_numeric(texto, errors="coerce")
    serial = pd.to_datetime(
        numero.where(numero.between(30000, 60000)),
        unit="D",
        origin="1899-12-30",
        errors="coerce",
    )

    return br.fillna(iso).fillna(serial)


BASE_DIR = Path(__file__).resolve().parent
ARQUIVOS = {
    "Japão": BASE_DIR / "jp.csv",
    "Coreia do Sul": BASE_DIR / "kr.csv",
}


MOEDAS = {
    "JPY": {"simbolo": "¥", "nome": "Iene japonês"},
    "KRW": {"simbolo": "₩", "nome": "Won sul-coreano"},
}

CATEGORIAS = {

    "Saques": [
        "seven bank", "atm", "withdraw", "saque", "lawson bank",
        "japan post bank", "e-net", "int'l",
    ],
    "Alimentação": [
        "familymart", "seven-eleven", "7-eleven", "sukiya", "mcdonald",
        "sushiro", "caffe", "cafe", "restaurant", "food", "bakery",
        "convenience", "gs25", "cu", "kakaomobi", "pascucci", "an kyoto",
        "shokkenkenbaiki", "81cafe", "spillout", "udon", "hinata", "ekibiru", 
    ],
    "Transporte": [
        "jr", "jrnishinihon", "jr east", "seven bank", "subway", "metro",
        "bus", "taxi", "train", "ktx", "t-money", "transport",
    ],
    "Compras": [
        "bic camera", "don quijote", "donquijote", "daiso", "gu co",
        "skechers", "columbia", "shopping", "store", "market", "mall",
        "traveler ter",
    ],
    "Hospedagem": [
        "hotel", "hostel", "airbnb", "booking", "lodging", "accommodation",
    ],
    "Saúde/Farmácia": [
        "drug", "pharmacy", "sundrug", "daikoku drug", "waizumato",
    ],
    "Lazer/Turismo": [
        "museum", "temple", "park", "tour", "ticket", "attraction",
        "panorama", "themuseumofkyoto", "arashiyama",
    ],
}

PALETA_CORES = px.colors.qualitative.Plotly
COR_PAISES = {
    "Japão": PALETA_CORES[0],
    "Coreia do Sul": PALETA_CORES[1],
}


TAXAS_PADRAO = {
    "JPY": 0.0355,  # 1 JPY em BRL
    "KRW": 0.0038,  # 1 KRW em BRL
}


@st.cache_data(ttl=30)
def carregar_dados():
    registros = []

    for pais, caminho in ARQUIVOS.items():
        if not caminho.exists():
            continue

        df = pd.read_csv(caminho, encoding="utf-8-sig")

        colunas_necessarias = {
            "Date", "Date Time", "Amount", "Currency", "Description",
            "Merchant", "Transaction Type", "Transaction Details Type",
        }

        faltantes = colunas_necessarias - set(df.columns)
        if faltantes:
            st.error(
                f"O arquivo `{caminho.name}` não possui as colunas esperadas: "
                f"{', '.join(sorted(faltantes))}"
            )
            continue

        df["País"] = pais
        df["Data"] = converter_datas(df["Date"])
        df["DataHora"] = pd.to_datetime(
            df["Date Time"], format="%d-%m-%Y %H:%M:%S.%f", errors="coerce"
        )
        df["Valor"] = pd.to_numeric(df["Amount"], errors="coerce")

        df["Merchant"] = (
            df["Merchant"]
            .fillna(df["Description"])
            .fillna("Não identificado")
        )

        df["Categoria"] = df["Merchant"].apply(classificar_categoria)

        gastos = df[
            (df["Transaction Type"] == "DEBIT")
            & (df["Transaction Details Type"] == "CARD")
            & (df["Valor"] < 0)
        ].copy()

        gastos["ValorAbsoluto"] = gastos["Valor"].abs()
        registros.append(gastos)

    if not registros:
        return pd.DataFrame()

    return pd.concat(registros, ignore_index=True)



def classificar_categoria(texto: str) -> str:
    texto = " " + re.sub(r"\s+", " ", str(texto).lower()).strip() + " "

    for categoria, palavras in CATEGORIAS.items():
        if any(palavra in texto for palavra in palavras):
            return categoria

    return "Outros"



def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_moeda(valor: float, moeda: str) -> str:
    simbolo = MOEDAS.get(moeda, {}).get("simbolo", "")
    return f"{simbolo} {valor:,.0f}".replace(",", ".")


def aplicar_filtros(df: pd.DataFrame):
    with st.sidebar:
        st.header(":material/filter_alt: Filtros")

        paises = st.multiselect(
            "País",
            options=sorted(df["País"].unique()),
            default=sorted(df["País"].unique()),
            placeholder='Selecione um país'
        )

        categorias = st.multiselect(
            "Categoria",
            options=sorted(df["Categoria"].unique()),
            default=sorted(df["Categoria"].unique()),
        )

        datas = df["Data"].dropna()
        data_min = datas.min().date()
        data_max = datas.max().date()

        periodo = st.date_input(
            "Período",
            value=(data_min, data_max),
            min_value=data_min,
            max_value=data_max,
        )

        if isinstance(periodo, tuple) and len(periodo) == 2:
            data_inicio, data_fim = periodo
        else:
            data_inicio, data_fim = data_min, data_max

        st.divider()
        st.header(":material/currency_exchange: Conversão para BRL")

        st.caption(
            "Informe a taxa usada para converter cada moeda para reais. "
            "O valor informado deve representar quanto **1 unidade da moeda estrangeira** vale em BRL."
        )

        taxa_jpy = st.number_input(
            "1 JPY = R$",
            min_value=0.000001,
            value=TAXAS_PADRAO["JPY"],
            step=0.0001,
            format="%.4f",
        )

        taxa_krw = st.number_input(
            "1 KRW = R$",
            min_value=0.000001,
            value=TAXAS_PADRAO["KRW"],
            step=0.0001,
            format="%.4f",
        )

        taxas = {
            "JPY": taxa_jpy,
            "KRW": taxa_krw,
        }

        st.caption(
            "Exemplo: se 100 JPY equivalem a R$ 3,55, informe **0,0355**. "
            "Se 1.000 KRW equivalem a R$ 3,80, informe **0,0038**."
        )

        st.divider()

        if st.button(":material/sync: Atualizar dados", width='stretch'):
            st.cache_data.clear()
            st.rerun()

    df_filtrado = df[
        df["País"].isin(paises)
        & df["Categoria"].isin(categorias)
        & df["Data"].between(pd.Timestamp(data_inicio), pd.Timestamp(data_fim))
    ].copy()

    df_filtrado["TaxaBRL"] = df_filtrado["Currency"].map(taxas)
    df_filtrado["ValorBRL"] = df_filtrado["ValorAbsoluto"] * df_filtrado["TaxaBRL"]

    return df_filtrado, taxas


def main():
    st.markdown("#### Controle de Gastos — Japão e Coreia do Sul")
    st.caption(
        ":material/trip: Relatório gerencial de gastos por país, dia, categoria e estabelecimento. "
        "Os valores são convertidos para BRL conforme as taxas informadas na sidebar."
    )

    df = carregar_dados()

    if df.empty:
        st.warning(
            "Nenhum gasto foi encontrado. Verifique se os arquivos `jp.csv` e `kr.csv` "
            "estão na pasta **Downloads** e se possuem as colunas da exportação da Wise."
        )
        return

    df_filtrado, taxas = aplicar_filtros(df)

    if df_filtrado.empty:
        st.info("Nenhum gasto corresponde aos filtros selecionados.")
        return

    total_brl = df_filtrado["ValorBRL"].sum()
    total_transacoes = len(df_filtrado)
    media_brl = total_brl / total_transacoes if total_transacoes else 0

    

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total da viagem", formatar_brl(total_brl), border=True)

    with col2:
        st.metric("Transações de gastos", f"{total_transacoes:,}".replace(",", "."), border=True)

    with col3:
        st.metric("Ticket médio", formatar_brl(media_brl), border=True)

    with col4:
        maior_gasto = df_filtrado.loc[df_filtrado["ValorBRL"].idxmax()]
        st.metric(
            "Maior gasto",
            formatar_brl(maior_gasto["ValorBRL"]),
            help=(
                f"{maior_gasto['Merchant']} — "
                f"{formatar_moeda(maior_gasto['ValorAbsoluto'], maior_gasto['Currency'])} "
                f"em {maior_gasto['Data'].strftime('%d/%m/%Y')}"
            ), border=True
        )

    # Totais por país
    totais_pais = (
        df_filtrado.groupby("País")
        .agg(
            TotalBRL=("ValorBRL", "sum"),
            Transacoes=("ValorBRL", "count"),
        )
        .reset_index()
        .sort_values("TotalBRL", ascending=False)
    )

    st.caption(":material/globe: Total por país")

    colunas_pais = st.columns(len(totais_pais))

    for i, linha in totais_pais.iterrows():
        with colunas_pais[i]:
            st.metric(
                label=linha["País"],
                value=formatar_brl(linha["TotalBRL"]),
                help=f"{linha['Transacoes']} transações",
                border=True
            )



    # Gastos por dia
    cols=st.columns(2)

    with cols[0]:
        
        st.caption(":material/calendar_month: Gastos por dia")
        with st.container(border=True, height=700):
            c=st.container(horizontal=True, width="stretch", horizontal_alignment="distribute")
            c.markdown('Gastos diários convertidos para BRL')
            modo_linha = c.toggle(
                ":material/show_chart: Exibir como linha",
                value=False,
                key="gastos_dia_linha",
            )

            gastos_dia = (
                df_filtrado.groupby(["Data", "País"])["ValorBRL"]
                .sum()
                .reset_index()
            )

            if modo_linha:
                fig_dia = px.line(
                    gastos_dia,
                    x="Data",
                    y="ValorBRL",
                    color="País",
                    markers=True,
                    labels={
                        "Data": "Data",
                        "ValorBRL": "Gasto (R$)",
                        "País": "País",
                    },
                    color_discrete_map=COR_PAISES,
                    text="ValorBRL",
                )

                fig_dia.update_traces(
                    texttemplate="R$ %{text:,.0f}",
                    textposition="top center",
                    cliponaxis=False,
                    line=dict(width=3),
                    marker=dict(size=8),
                )
            else:
                fig_dia = px.bar(
                    gastos_dia,
                    x="Data",
                    y="ValorBRL",
                    color="País",

                    labels={
                        "Data": "Data",
                        "ValorBRL": "Gasto (R$)",
                        "País": "País",
                    },
                    color_discrete_map=COR_PAISES,
                    text="ValorBRL",
                )

                fig_dia.update_traces(
                    texttemplate="R$ %{text:,.0f}",
                    textposition="inside",
                    insidetextanchor="end",
                    textangle=-90,
                    cliponaxis=False,
                )

            fig_dia.update_layout(
                height=520,
                bargap=0.15,
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.15,
                    xanchor="center",
                    x=0.5,
                    title_text="",
                ),
                margin=dict(b=80),
            )

            fig_dia.update_yaxes(
                showticklabels=False,
                showgrid=False,
                zeroline=False,
                title=None,
            )

            
            st.plotly_chart(fig_dia, width='content')


    with cols[1]:
        st.caption(":material/label: Gastos por categoria")
        # Categorias
        with st.container(border=True, height=700):
            st.markdown("Distribuição dos gastos por categoria em BRL",)

            gastos_categoria = (
                df_filtrado.groupby(["País", "Categoria"])["ValorBRL"]
                .sum()
                .reset_index()
            )

            fig_categoria = px.bar(
                gastos_categoria,
                x="ValorBRL",
                y="Categoria",
                color="País",
                orientation="h",
                barmode="group",
                labels={
                    "Categoria": "Categoria",
                    "ValorBRL": "Gasto (R$)",
                    "País": "País",
                },
                color_discrete_map=COR_PAISES,
                text="ValorBRL",
            )

            fig_categoria.update_traces(
                texttemplate="R$ %{text:,.2f}",
                textposition="outside",
                cliponaxis=False,
            )

            fig_categoria.update_layout(
                height=560,
                bargap=0.25,
                uniformtext_minsize=9,
                uniformtext_mode="hide",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.15,
                    xanchor="center",
                    x=0.5,
                    title_text="",
                ),
                margin=dict(b=80),
            )

            fig_categoria.update_yaxes(autorange="reversed", title=None)
            fig_categoria.update_xaxes(tickprefix="R$ ")

            st.plotly_chart(fig_categoria, width='stretch')



    # Estabelecimentos
    st.caption(":material/storefront: Principais estabelecimentos")
    with st.container(border=True):
        st.markdown("Top 10 estabelecimentos por gasto em BRL")
        top_merchant = (
            df_filtrado.groupby(["País", "Merchant"])["ValorBRL"]
            .sum()
            .reset_index()
            .sort_values("ValorBRL", ascending=False)
        )

        top_10 = top_merchant.groupby("País").head(10)

        fig_merchant = px.bar(
            top_10,
            x="ValorBRL",
            y="Merchant",
            color="País",
            orientation="h",
            labels={
                "Merchant": "Estabelecimento",
                "ValorBRL": "Gasto (R$)",
                "País": "País",
            },
            color_discrete_map=COR_PAISES,
            text="ValorBRL",
        )

        fig_merchant.update_traces(
            texttemplate="R$ %{text:,.2f}",
            textposition="inside",
            insidetextanchor="end",
            cliponaxis=False,
        )

        fig_merchant.update_layout(
            height=620,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.5,
                title_text="",
            ),
            margin=dict(b=80),
        )

        fig_merchant.update_yaxes(autorange="reversed", title=None)
        fig_merchant.update_xaxes(tickprefix="R$ ")

        st.plotly_chart(fig_merchant, width='stretch')


    # Tabela detalhada
    st.caption(":material/checkbook: Transações filtradas")

    tabela = df_filtrado[
        [
            "Data",
            "País",
            "Currency",
            "Categoria",
            "Merchant",
            "ValorAbsoluto",
            "TaxaBRL",
            "ValorBRL",
            "Description",
        ]
    ].copy()

    tabela = tabela.sort_values(
        ["Data", "País", "ValorBRL"],
        ascending=[False, True, False],
    )

    tabela = tabela.rename(
        columns={
            "Data": "Data",
            "País": "País",
            "Currency": "Moeda original",
            "Categoria": "Categoria",
            "Merchant": "Estabelecimento",
            "ValorAbsoluto": "Valor original",
            "TaxaBRL": "Taxa BRL",
            "ValorBRL": "Valor em BRL",
            "Description": "Descrição",
        }
    )

    st.dataframe(
        tabela,
        width='content',
        hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Valor original": st.column_config.NumberColumn(
                "Valor original",
                format="%.0f",
            ),
            "Taxa BRL": st.column_config.NumberColumn(
                "Taxa BRL",
                format="%.6f",
            ),
            "Valor em BRL": st.column_config.NumberColumn(
                "Valor em BRL",
                format="R$ %.2f",
            ),
        },
    )

    # Exportação
    csv = tabela.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    st.download_button(
        label=":material/download: Baixar relatório filtrado em CSV",
        data=csv,
        file_name="relatorio_gastos_viagem_brl.csv",
        mime="text/csv",
        type="primary"
    )

    st.divider()
    st.caption(
        f"Última leitura dos arquivos: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')} · "
        "Clique em **Atualizar dados** na sidebar após atualizar o `kr.csv`."
    )


if __name__ == "__main__":
    main()
