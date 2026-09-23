import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import pandas as pd
import streamlit as st

def _sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", str(url))
    if not m:
        raise ValueError("Link do Google Sheets inválido ou não reconhecido.")
    return m.group(1)

def google_sheet_csv_url(url: str, gid: str = "0") -> str:
    url = str(url).strip()
    if "COLE_AQUI" in url or not url:
        raise ValueError("Configure o link da planilha em config.py.")
    if "output=csv" in url or "format=csv" in url:
        return url
    sid = _sheet_id(url)
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"

@st.cache_data(ttl=600, show_spinner=False)
def load_google_sheet(url: str, gid: str = "0") -> pd.DataFrame:
    csv_url = google_sheet_csv_url(url, gid)
    return pd.read_csv(csv_url, dtype=str)

def clean_text(value):
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())

def normalize_key(value: str) -> str:
    s = clean_text(value).upper()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    return s

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [normalize_key(c) for c in out.columns]
    aliases = {
        "NUMERO ST": "NUMERO ST",
        "DATA HORA CHAMADO": "DATA HORA CHAMADO",
        "DATA HORA SOLUCAO": "DATA HORA SOLUCAO",
        "SERVICO PROBLEMA RELATADO": "SERVICO PROBLEMA RELATADO",
        "TIPO DE MANUTENCAO": "TIPO DE MANUTENCAO",
        "TEMPO SOLUCAO": "TEMPO SOLUCAO",
        "OBSERVACAO": "OBSERVACAO",
        "TECNICO": "TECNICO",
    }
    out = out.rename(columns={c: aliases.get(c, c) for c in out.columns})
    return out

def prepare_chamados(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    required = [
        "CLIENTE", "NUMERO ST", "CIDADE", "MARCA", "MODELO",
        "DATA HORA CHAMADO", "DATA HORA SOLUCAO", "TECNICO", "STATUS",
        "SERVICO PROBLEMA RELATADO", "TIPO DE MANUTENCAO",
        "TEMPO SOLUCAO", "OBSERVACAO"
    ]
    for col in required:
        if col not in df.columns:
            df[col] = ""

    for col in required:
        if col not in ("DATA HORA CHAMADO", "DATA HORA SOLUCAO"):
            df[col] = df[col].map(clean_text)

    df["STATUS"] = df["STATUS"].map(normalize_key)
    df["DATA HORA CHAMADO"] = pd.to_datetime(
        df["DATA HORA CHAMADO"], dayfirst=True, errors="coerce"
    )
    df["DATA HORA SOLUCAO"] = pd.to_datetime(
        df["DATA HORA SOLUCAO"], dayfirst=True, errors="coerce"
    )
    df = df[df["CLIENTE"].astype(str).str.strip().ne("")].copy()
    return df

def parse_br_number(value) -> float:
    if value is None or pd.isna(value):
        return 0.0
    s = str(value).strip().replace("R$", "").replace(" ", "")
    if not s:
        return 0.0
    # pt-BR: 153.071,56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # preserve decimal dot if already numeric-looking
        s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0

def extract_first_numeric(df: pd.DataFrame, preferred_column="VENDIDO") -> float:
    df = normalize_columns(df)
    if preferred_column in df.columns:
        for v in df[preferred_column]:
            n = parse_br_number(v)
            if n != 0:
                return n
    for col in df.columns:
        for v in df[col]:
            n = parse_br_number(v)
            if n != 0:
                return n
    return 0.0
