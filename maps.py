from pathlib import Path
import html
import math
import hashlib

import pandas as pd
import streamlit as st
from geopy.geocoders import ArcGIS
from geopy.extra.rate_limiter import RateLimiter
import folium

CACHE_FILE = Path(__file__).resolve().parents[1] / "assets" / "geocode_cache.csv"

KNOWN_CITIES = {
    "Passo Fundo": (-28.2628, -52.4067),
    "Não Me Toque": (-28.4592, -52.8203),
    "Não-Me-Toque": (-28.4592, -52.8203),
    "Lages": (-27.8150, -50.3259),
    "Rio Grande": (-32.0350, -52.0986),
    "Canoas": (-29.9177, -51.1833),
    "Mostardas": (-31.1054, -50.9214),
    "Santa Cruz do Sul": (-29.7175, -52.4258),
    "Lajeado": (-29.4669, -51.9614),
    "Erechim": (-27.6346, -52.2730),
    "Paraíso": (-26.6139, -53.6719),
    "Palma Sola": (-26.3471, -53.2777),
    "São José do Cedro": (-26.4561, -53.4955),
    "Venâncio Aires": (-29.6064, -52.1919),
    "Santiago": (-29.1917, -54.8674),
    "Sarandi": (-27.9439, -52.9231),
    "Ituporanga": (-27.4102, -49.5962),
    "Jacinto Machado": (-28.9960, -49.7620),
    "Morrinhos do Sul": (-29.3578, -49.9317),
    "Caxias do Sul": (-29.1678, -51.1794),
    "Praia Grande": (-29.1954, -49.9526),
    "Criciúma": (-28.6775, -49.3697),
    "Palmeira das Missões": (-27.8994, -53.3137),
    "Santo Augusto": (-27.8526, -53.7778),
    "Igrejinha": (-29.5743, -50.7904),
    "Nova Prata": (-28.7830, -51.6104),
    "São José": (-27.6136, -48.6366),
}

def _load_cache():
    if CACHE_FILE.exists():
        try:
            df = pd.read_csv(CACHE_FILE)
            if {"query", "lat", "lon"}.issubset(df.columns):
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=["query", "lat", "lon"])

def _save_cache(df):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        df.drop_duplicates("query", keep="last").to_csv(CACHE_FILE, index=False)
    except Exception:
        pass

def _normalize_city(city):
    if pd.isna(city):
        return ""
    return " ".join(str(city).strip().split())

def _query_for_city(city, uf_overrides=None, query_overrides=None):
    city = _normalize_city(city)
    if query_overrides and city in query_overrides:
        return query_overrides[city]

    uf = (uf_overrides or {}).get(city)
    if uf:
        return f"{city}, {uf}, Brasil"

    return f"{city}, Brasil"

@st.cache_data(ttl=86400, show_spinner=False)
def geocode_cities(cities_tuple, uf_overrides=None, query_overrides=None):
    cities = sorted({_normalize_city(c) for c in cities_tuple if _normalize_city(c)})

    cache = _load_cache()
    known_cache = {}
    if not cache.empty:
        for _, row in cache.dropna(subset=["lat", "lon"]).iterrows():
            known_cache[str(row["query"])] = (float(row["lat"]), float(row["lon"]))

    geolocator = ArcGIS(timeout=8)
    geocode = RateLimiter(
        geolocator.geocode,
        min_delay_seconds=0.25,
        max_retries=1,
        error_wait_seconds=1,
        swallow_exceptions=True,
    )

    rows = []
    changed = False

    for city in cities:
        if city in KNOWN_CITIES:
            lat, lon = KNOWN_CITIES[city]
            rows.append({"CIDADE": city, "LAT": lat, "LON": lon})
            continue

        query = _query_for_city(city, uf_overrides, query_overrides)

        if query in known_cache:
            lat, lon = known_cache[query]
            rows.append({"CIDADE": city, "LAT": lat, "LON": lon})
            continue

        lat = lon = None
        try:
            loc = geocode(query, exactly_one=True)
            if loc is not None:
                lat, lon = float(loc.latitude), float(loc.longitude)
        except Exception:
            pass

        if lat is not None and lon is not None:
            cache = pd.concat(
                [cache, pd.DataFrame([{"query": query, "lat": lat, "lon": lon}])],
                ignore_index=True
            )
            changed = True

        rows.append({"CIDADE": city, "LAT": lat, "LON": lon})

    if changed:
        _save_cache(cache)

    return pd.DataFrame(rows)

def _safe(v):
    return html.escape("" if pd.isna(v) else str(v))

def _duration_text(value):
    if value is None or pd.isna(value):
        return "—"
    seconds = max(0, int(value.total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours = rem // 3600
    return f"{days} dias {hours} h" if days else f"{hours} h"

def _spread_same_city(data: pd.DataFrame) -> pd.DataFrame:
    """
    Se vários chamados usam a mesma coordenada da cidade, distribui os pontos
    ao redor do centro em um pequeno círculo para que cada máquina fique visível.
    """
    out = data.copy()
    out["PLOT_LAT"] = out["LAT"]
    out["PLOT_LON"] = out["LON"]

    for city, idxs in out.groupby("CIDADE").groups.items():
        idxs = list(idxs)
        n = len(idxs)

        if n <= 1:
            continue

        base_lat = float(out.loc[idxs[0], "LAT"])
        base_lon = float(out.loc[idxs[0], "LON"])

        # Raio visual pequeno (~1 a 3 km dependendo da latitude).
        # Aumenta levemente quando há muitos pontos.
        radius = 0.010 + min(n, 12) * 0.0012

        for i, idx in enumerate(idxs):
            angle = 2 * math.pi * i / n
            lat_offset = radius * math.sin(angle)
            lon_offset = (radius * math.cos(angle)) / max(math.cos(math.radians(base_lat)), 0.35)

            out.at[idx, "PLOT_LAT"] = base_lat + lat_offset
            out.at[idx, "PLOT_LON"] = base_lon + lon_offset

    return out

def build_map(df, status_label, uf_overrides=None, query_overrides=None):
    # Sem CartoDB para evitar a mensagem "API KEY REQUIRED".
    mapa = folium.Map(
        location=[-29.1, -51.2],
        zoom_start=6,
        tiles="OpenStreetMap",
        control_scale=False,
        prefer_canvas=True,
    )

    if df is None or df.empty:
        return mapa

    geo = geocode_cities(
        tuple(df["CIDADE"].dropna().astype(str).unique()),
        uf_overrides,
        query_overrides
    )

    data = df.merge(geo, on="CIDADE", how="left")
    data = data.dropna(subset=["LAT", "LON"]).copy()

    # Sem cluster: cada chamado aparece como ponto separado.
    data = _spread_same_city(data)

    for _, row in data.iterrows():
        chamado = row.get("DATA HORA CHAMADO")
        chamado_txt = chamado.strftime("%d/%m/%Y %H:%M") if pd.notna(chamado) else "—"

        popup = f"""
        <div style="font-family:Arial;min-width:285px;color:#111">
          <b style="font-size:15px">{_safe(row.get('CLIENTE'))}</b><br><br>
          <b>Cidade:</b> {_safe(row.get('CIDADE'))}<br>
          <b>Máquina:</b> {_safe(row.get('MARCA'))} {_safe(row.get('MODELO'))}<br>
          <b>Nº ST:</b> {_safe(row.get('NUMERO ST'))}<br>
          <b>Chamado:</b> {chamado_txt}<br>
          <b>Tempo:</b> {_duration_text(row.get('DURACAO'))}<br>
          <b>Serviço:</b> {_safe(row.get('SERVICO PROBLEMA RELATADO'))}<br>
          <b>Tipo:</b> {_safe(row.get('TIPO DE MANUTENCAO'))}<br>
          <b>Observação:</b> {_safe(row.get('OBSERVACAO'))}
        </div>
        """

        folium.CircleMarker(
            location=[row["PLOT_LAT"], row["PLOT_LON"]],
            radius=7,
            color="#BED600",
            weight=2,
            fill=True,
            fill_color="#BED600",
            fill_opacity=0.95,
            popup=folium.Popup(popup, max_width=390),
            tooltip=_safe(row.get("CLIENTE")),
        ).add_to(mapa)

    return mapa
