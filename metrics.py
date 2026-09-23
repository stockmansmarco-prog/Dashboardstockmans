from datetime import datetime
import math
import pandas as pd

def format_duration(td) -> str:
    if td is None or pd.isna(td):
        return "—"
    seconds = max(0, int(td.total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} dias {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"

def format_currency_br(value: float) -> str:
    s = f"{float(value):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def calculate_waiting(df: pd.DataFrame, now=None) -> pd.DataFrame:
    out = df.copy()
    now = pd.Timestamp(now or datetime.now())
    out["DURACAO"] = now - out["DATA HORA CHAMADO"]
    out.loc[out["DATA HORA CHAMADO"].isna(), "DURACAO"] = pd.NaT
    return out

def calculate_solved(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["DURACAO"] = out["DATA HORA SOLUCAO"] - out["DATA HORA CHAMADO"]
    invalid = (
        out["DATA HORA CHAMADO"].isna()
        | out["DATA HORA SOLUCAO"].isna()
        | (out["DURACAO"] < pd.Timedelta(0))
    )
    out.loc[invalid, "DURACAO"] = pd.NaT
    return out

def average_duration(df: pd.DataFrame):
    vals = df["DURACAO"].dropna()
    if vals.empty:
        return None
    return vals.mean()

def goal_percent(sold: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return (sold / target) * 100.0

def percent_br(value: float) -> str:
    return f"{value:.2f}%".replace(".", ",")

def top_waiting(df: pd.DataFrame, n=5) -> pd.DataFrame:
    return df.dropna(subset=["DURACAO"]).sort_values("DURACAO", ascending=False).head(n)


# =========================
# NOVAS MÉTRICAS
# =========================

def top_clients_by_calls(df: pd.DataFrame, months: int = 3, n: int = 5, now=None) -> pd.DataFrame:
    """
    Top N clientes com mais chamados abertos nos últimos `months` meses corridos
    (janela móvel contando a partir de agora, incluindo o mês atual parcial).
    Considera TODOS os chamados (independente do status atual).
    """
    now = pd.Timestamp(now or datetime.now())
    cutoff = now - pd.DateOffset(months=months)

    recent = df[df["DATA HORA CHAMADO"].notna() & (df["DATA HORA CHAMADO"] >= cutoff)]

    if recent.empty:
        return pd.DataFrame(columns=["CLIENTE", "QTD"])

    counts = (
        recent.groupby("CLIENTE")
        .size()
        .reset_index(name="QTD")
        .sort_values("QTD", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    return counts


def monthly_finalized_counts(df: pd.DataFrame, months: int = 5, now=None) -> pd.DataFrame:
    """
    Quantidade de chamados com STATUS = SOLUCIONADO, agrupados por mês de
    conclusão (DATA HORA SOLUCAO), cobrindo os últimos `months` meses corridos
    (inclui o mês atual, mesmo que parcial). Meses sem nenhum chamado
    finalizado aparecem com QTD = 0.
    """
    now = pd.Timestamp(now or datetime.now())
    cutoff = now - pd.DateOffset(months=months)

    solved = df[
        df["STATUS"].eq("SOLUCIONADO")
        & df["DATA HORA SOLUCAO"].notna()
        & (df["DATA HORA SOLUCAO"] >= cutoff)
    ].copy()

    if solved.empty:
        month_range = pd.period_range(
            (now - pd.DateOffset(months=months - 1)).to_period("M"),
            now.to_period("M"),
            freq="M",
        )
        out = pd.DataFrame({"MES": month_range, "QTD": 0})
    else:
        solved["MES"] = solved["DATA HORA SOLUCAO"].dt.to_period("M")
        counts = solved.groupby("MES").size()

        month_range = pd.period_range(
            (now - pd.DateOffset(months=months - 1)).to_period("M"),
            now.to_period("M"),
            freq="M",
        )
        counts = counts.reindex(month_range, fill_value=0)
        out = counts.reset_index()
        out.columns = ["MES", "QTD"]

    out["MES_LABEL"] = out["MES"].dt.strftime("%b/%y").str.upper()
    return out
