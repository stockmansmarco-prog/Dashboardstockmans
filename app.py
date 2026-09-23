from datetime import datetime
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

from config import (
    CHAMADOS_SHEET_URL, CHAMADOS_GID,
    META_PECAS_SHEET_URL, META_PECAS_GID,
    META_MO_SHEET_URL, META_MO_GID,
    META_PECAS_TOTAL, META_MO_TOTAL,
    PAGE_ROTATION_SECONDS, CITY_QUERY_OVERRIDES, CITY_UF_OVERRIDES
)
from utils.data import load_google_sheet, prepare_chamados, extract_first_numeric
from utils.metrics import (
    calculate_waiting, calculate_solved, average_duration, format_duration,
    format_currency_br, goal_percent, percent_br, top_waiting,
    top_clients_by_calls, monthly_finalized_counts
)
from utils.maps import build_map

st.set_page_config(
    page_title="Stockmans | Pós-Venda",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# O tick de autorefresh dirige a troca de telas (ver PAGE_ROTATION_SECONDS).
# Os DADOS não são recarregados a cada tick: eles ficam em cache por
# CACHE_TTL_SECONDS (config.py) e só são buscados de novo quando o cache vence.
st_autorefresh(interval=PAGE_ROTATION_SECONDS * 1000, key="stockmans_auto_refresh")

st.markdown("""
<style>
:root{
  --bg:#06131f; --panel:#0b1d2b; --panel2:#102636; --line:#20394a;
  --text:#f3f6f8; --muted:#8fa5b5; --green:#BED600; --danger:#ff5d5d;
}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--text);}
[data-testid="stHeader"]{background:rgba(0,0,0,0);}
[data-testid="stToolbar"], #MainMenu, footer{visibility:hidden;}
.block-container{max-width:1800px;padding:1.1rem 1.5rem 1rem;}
.stock-header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);padding:0 0 14px;margin-bottom:12px}
.stock-title{font-size:1.45rem;font-weight:800;letter-spacing:.08em;color:var(--text)}
.stock-sub{font-size:.72rem;letter-spacing:.18em;color:var(--muted);margin-top:2px}
.kpi{height:142px;background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-sizing:border-box}
.kpi-label{font-size:.78rem;font-weight:700;letter-spacing:.06em;color:#cbd6dd}
.kpi-value{font-size:2.2rem;font-weight:850;line-height:1.15;margin-top:10px;color:var(--text)}
.kpi-sub{font-size:.75rem;color:var(--muted);margin-top:5px}
.progress{height:7px;background:#2a4050;border-radius:99px;overflow:hidden;margin-top:12px}
.progress>span{display:block;height:100%;background:var(--green);border-radius:99px}
.panel-title{font-size:1rem;font-weight:800;letter-spacing:.04em;margin:2px 0 2px}
.panel-sub{font-size:.68rem;color:var(--muted);letter-spacing:.13em;margin-bottom:8px}
.page-label{font-size:.72rem;font-weight:700;letter-spacing:.14em;color:var(--muted);text-align:right}
.rank-row{display:grid;grid-template-columns:34px 1.35fr 1fr .9fr;gap:10px;align-items:center;padding:17px 0;border-bottom:1px solid var(--line)}
.rank-pos{font-size:1.35rem;font-weight:900;color:var(--green)}
.rank-client{font-weight:750}.rank-city{color:#c7d2da;font-size:.86rem}
.rank-time{font-size:1rem;font-weight:850;text-align:right}
.foot{margin-top:10px;border-top:1px solid var(--line);padding-top:10px;color:var(--muted);font-size:.7rem;text-align:right;letter-spacing:.05em;display:flex;align-items:center;justify-content:flex-end;gap:12px}
.page-dots{display:inline-flex;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;background:#2a4050;display:inline-block}
.dot.active{background:var(--green)}
div[data-testid="stRadio"] > label{display:none}
div[data-testid="stRadio"] div[role="radiogroup"]{justify-content:flex-end;gap:4px}
div[data-testid="stRadio"] label{background:var(--panel);border:1px solid var(--line);padding:6px 12px;border-radius:999px}
div[data-testid="stRadio"] label:has(input:checked){background:var(--green);color:#06131f;border-color:var(--green)}
iframe{border-radius:12px}
div[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(145deg,var(--panel),var(--panel2));border-color:var(--line)!important;border-radius:14px!important;min-height:640px;box-sizing:border-box}
@media(max-width:900px){.kpi{height:auto;min-height:125px}.rank-row{grid-template-columns:30px 1fr}.rank-city,.rank-time{text-align:left}}
</style>
""", unsafe_allow_html=True)

def kpi_card(label, value, sub="", progress=None):
    p = ""
    if progress is not None:
        width = max(0, min(float(progress), 100))
        p = f'<div class="progress"><span style="width:{width}%"></span></div>'
    st.markdown(
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>{p}</div>',
        unsafe_allow_html=True
    )

# =========================
# TELAS ROTATIVAS
# =========================
# Adicione um novo id nesta lista para criar mais uma tela no futuro.
# A troca é sincronizada pelo relógio, então todas as TVs mostram a
# mesma tela ao mesmo tempo, mesmo que reiniciem o navegador.
PAGES = ["operacional", "indicadores"]

now_ts = int(datetime.now().timestamp())
page_index = (now_ts // PAGE_ROTATION_SECONDS) % len(PAGES)
current_page = PAGES[page_index]

# Header (comum a todas as telas)
h1, h2, h3 = st.columns([1.0, 2.0, 1.1], vertical_alignment="center")
with h1:
    logo = Path("assets/logo_stockmans.png")
    if logo.exists():
        st.image(str(logo), width=310)
    else:
        st.markdown("### STOCKMANS")
with h2:
    st.markdown('<div class="stock-title">DASHBOARD PÓS-VENDA</div><div class="stock-sub">ACOMPANHAMENTO OPERACIONAL</div>', unsafe_allow_html=True)
with h3:
    if current_page == "operacional":
        status = st.radio("Status", ["AGUARDANDO", "SOLUCIONADO"], horizontal=True, label_visibility="collapsed")
    else:
        status = "AGUARDANDO"
        st.markdown('<div class="page-label">INDICADORES GERAIS</div>', unsafe_allow_html=True)

# Data (carregado sempre; o cache evita releitura constante do Google Sheets)
try:
    chamados = prepare_chamados(load_google_sheet(CHAMADOS_SHEET_URL, CHAMADOS_GID))
    pecas_df = load_google_sheet(META_PECAS_SHEET_URL, META_PECAS_GID)
    mo_df = load_google_sheet(META_MO_SHEET_URL, META_MO_GID)
except Exception as e:
    st.error(f"Não foi possível carregar as planilhas. Verifique config.py e o acesso aos Google Sheets. Detalhe: {e}")
    st.stop()

vendido_pecas = extract_first_numeric(pecas_df, "VENDIDO")
vendido_mo = extract_first_numeric(mo_df, "VENDIDO")
pct_pecas = goal_percent(vendido_pecas, META_PECAS_TOTAL)
pct_mo = goal_percent(vendido_mo, META_MO_TOTAL)

# =========================
# TELA 1: OPERACIONAL (KPIs + mapa + ranking)
# =========================
if current_page == "operacional":
    base = chamados[chamados["STATUS"].eq(status)].copy()

    if status == "AGUARDANDO":
        base = calculate_waiting(base)
        count_label = "MÁQUINAS AGUARDANDO"
        avg_label = "TEMPO MÉDIO AGUARDANDO"
        map_title = "MÁQUINAS AGUARDANDO ATENDIMENTO"
    else:
        base = calculate_solved(base)
        count_label = "MÁQUINAS SOLUCIONADAS"
        avg_label = "TEMPO MÉDIO DE SOLUÇÃO"
        map_title = "ATENDIMENTOS SOLUCIONADOS"

    avg = average_duration(base)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card(count_label, f"{len(base):,}".replace(",", "."))
    with c2:
        kpi_card(avg_label, format_duration(avg))
    with c3:
        kpi_card("META PEÇAS", percent_br(pct_pecas),
                 f"{format_currency_br(vendido_pecas)} de {format_currency_br(META_PECAS_TOTAL)}",
                 pct_pecas)
    with c4:
        kpi_card("META MÃO DE OBRA", percent_br(pct_mo),
                 f"{format_currency_br(vendido_mo)} de {format_currency_br(META_MO_TOTAL)}",
                 pct_mo)

    st.write("")
    left, right = st.columns([1.55, 1.0], gap="medium")

    with left:
        st.markdown(f'<div class="panel-title">{map_title}</div><div class="panel-sub">LOCALIZAÇÃO DOS CLIENTES NO RS E SC</div>', unsafe_allow_html=True)
        mapa = build_map(base, status, CITY_UF_OVERRIDES, CITY_QUERY_OVERRIDES)
        st_folium(mapa, width=None, height=640, returned_objects=[])

    with right:
        with st.container(border=True):
            if status == "AGUARDANDO":
                st.markdown(
                    '<div class="panel-title">CLIENTES AGUARDANDO HÁ MAIS TEMPO</div>'
                    '<div class="panel-sub">TOP 5 · CHAMADOS EM ABERTO</div>',
                    unsafe_allow_html=True
                )

                top5 = top_waiting(base, 5)

                if top5.empty:
                    st.markdown(
                        '<div style="color:#8fa5b5;padding:30px 0">'
                        'Nenhum chamado aguardando com data válida.'
                        '</div>',
                        unsafe_allow_html=True
                    )
                else:
                    for pos, (_, r) in enumerate(top5.iterrows(), 1):
                        cpos, ccli, ccid, ctempo = st.columns([0.12, 1.05, 0.85, 0.72], vertical_alignment="center")
                        with cpos:
                            st.markdown(f'<div class="rank-pos">{pos}</div>', unsafe_allow_html=True)
                        with ccli:
                            st.markdown(f'<div class="rank-client">{r["CLIENTE"]}</div>', unsafe_allow_html=True)
                        with ccid:
                            st.markdown(f'<div class="rank-city">{r["CIDADE"]}</div>', unsafe_allow_html=True)
                        with ctempo:
                            st.markdown(f'<div class="rank-time">{format_duration(r["DURACAO"])}</div>', unsafe_allow_html=True)
                        st.markdown('<div style="height:1px;background:#20394a;margin:8px 0 6px;"></div>', unsafe_allow_html=True)

            else:
                st.markdown(
                    '<div class="panel-title">ÚLTIMOS ATENDIMENTOS SOLUCIONADOS</div>'
                    '<div class="panel-sub">CHAMADOS CONCLUÍDOS</div>',
                    unsafe_allow_html=True
                )

                solved = (
                    base.dropna(subset=["DATA HORA SOLUCAO"])
                    .sort_values("DATA HORA SOLUCAO", ascending=False)
                    .head(5)
                )

                if solved.empty:
                    st.markdown(
                        '<div style="color:#8fa5b5;padding:30px 0">'
                        'Nenhum chamado solucionado com data válida.'
                        '</div>',
                        unsafe_allow_html=True
                    )
                else:
                    for pos, (_, r) in enumerate(solved.iterrows(), 1):
                        cpos, ccli, ccid, ctempo = st.columns([0.12, 1.05, 0.85, 0.72], vertical_alignment="center")
                        with cpos:
                            st.markdown(f'<div class="rank-pos">{pos}</div>', unsafe_allow_html=True)
                        with ccli:
                            st.markdown(f'<div class="rank-client">{r["CLIENTE"]}</div>', unsafe_allow_html=True)
                        with ccid:
                            st.markdown(f'<div class="rank-city">{r["CIDADE"]}</div>', unsafe_allow_html=True)
                        with ctempo:
                            st.markdown(f'<div class="rank-time">{format_duration(r["DURACAO"])}</div>', unsafe_allow_html=True)
                        st.markdown('<div style="height:1px;background:#20394a;margin:8px 0 6px;"></div>', unsafe_allow_html=True)

# =========================
# TELA 2: INDICADORES (gráfico mensal + top clientes)
# =========================
else:
    st.write("")
    left, right = st.columns([1.55, 1.0], gap="medium")

    with left:
        with st.container(border=True):
            st.markdown(
                '<div class="panel-title">CHAMADOS FINALIZADOS POR MÊS</div>'
                '<div class="panel-sub">ÚLTIMOS 5 MESES CORRIDOS</div>',
                unsafe_allow_html=True
            )

            monthly = monthly_finalized_counts(chamados, months=5)

            fig = px.bar(monthly, x="MES_LABEL", y="QTD", text="QTD")
            fig.update_traces(
                marker_color="#BED600",
                textposition="outside",
                textfont_color="#f3f6f8",
                textfont_size=16
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#f3f6f8",
                font_size=15,
                margin=dict(l=10, r=10, t=10, b=10),
                height=560,
                xaxis_title=None,
                yaxis_title=None,
                xaxis=dict(showgrid=False, tickfont=dict(size=16)),
                yaxis=dict(showgrid=True, gridcolor="#20394a"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with right:
        with st.container(border=True):
            st.markdown(
                '<div class="panel-title">TOP 5 CLIENTES · MAIS CHAMADOS</div>'
                '<div class="panel-sub">ÚLTIMOS 3 MESES CORRIDOS</div>',
                unsafe_allow_html=True
            )

            top_clients = top_clients_by_calls(chamados, months=3, n=5)

            if top_clients.empty:
                st.markdown(
                    '<div style="color:#8fa5b5;padding:30px 0">'
                    'Nenhum chamado no período.'
                    '</div>',
                    unsafe_allow_html=True
                )
            else:
                for pos, (_, r) in enumerate(top_clients.iterrows(), 1):
                    cpos, ccli, cqtd = st.columns([0.15, 1.55, 0.5], vertical_alignment="center")
                    with cpos:
                        st.markdown(f'<div class="rank-pos">{pos}</div>', unsafe_allow_html=True)
                    with ccli:
                        st.markdown(f'<div class="rank-client">{r["CLIENTE"]}</div>', unsafe_allow_html=True)
                    with cqtd:
                        st.markdown(f'<div class="rank-time">{int(r["QTD"])}</div>', unsafe_allow_html=True)
                    st.markdown('<div style="height:1px;background:#20394a;margin:8px 0 6px;"></div>', unsafe_allow_html=True)

# =========================
# RODAPÉ: indicador de tela + última atualização
# =========================
dots_html = "".join(
    f'<span class="dot{" active" if i == page_index else ""}"></span>'
    for i in range(len(PAGES))
)
st.markdown(
    f'<div class="foot"><span class="page-dots">{dots_html}</span>'
    f'ÚLTIMA ATUALIZAÇÃO: {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>',
    unsafe_allow_html=True
)
