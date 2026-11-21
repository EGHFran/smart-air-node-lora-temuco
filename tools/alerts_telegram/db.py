from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, text

from tools.alerts_telegram.config import COL_FECHA, COL_NODO, DATABASE_URL, DB_TZ, NODO_ID, TABLA, TZ, VARIABLES

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
_q = engine.dialect.identifier_preparer.quote  # entrecomilla según el motor (`timestamp` en MySQL)


def ahora() -> datetime:
    return datetime.now(ZoneInfo(TZ))


def _a_db(dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo(DB_TZ)).replace(tzinfo=None)


def leer(desde: datetime, hasta: datetime | None = None) -> pd.DataFrame:
    """Devuelve las mediciones en [desde, hasta) con fechas en hora local (TZ)."""
    fecha = _q(COL_FECHA)
    cols = ", ".join(f"{_q(cfg['columna'])} AS {clave}" for clave, cfg in VARIABLES.items())
    sql = f"SELECT {fecha} AS fecha, {cols} FROM {_q(TABLA)} WHERE {fecha} >= :desde"
    params = {"desde": _a_db(desde)}
    if hasta is not None:
        sql += f" AND {fecha} < :hasta"
        params["hasta"] = _a_db(hasta)
    if NODO_ID:
        sql += f" AND {_q(COL_NODO)} = :nodo"
        params["nodo"] = NODO_ID
    sql += " ORDER BY fecha"

    df = pd.read_sql(text(sql), engine, params=params)
    if df.empty:
        return df

    df["fecha"] = pd.to_datetime(df["fecha"])
    if df["fecha"].dt.tz is None:
        df["fecha"] = df["fecha"].dt.tz_localize(DB_TZ, ambiguous="NaT", nonexistent="shift_forward")
    df["fecha"] = df["fecha"].dt.tz_convert(TZ)
    df = df.dropna(subset=["fecha"])
    for c in VARIABLES:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df
