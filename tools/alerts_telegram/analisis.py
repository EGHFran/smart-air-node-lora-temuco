import numpy as np
import pandas as pd

from tools.alerts_telegram.config import VARIABLES


def resumen(df: pd.DataFrame) -> dict:
    """Promedio, mínimo, pico y % de lecturas sobre la norma por variable."""
    out = {}
    for var, cfg in VARIABLES.items():
        s = df[var].dropna()
        if s.empty:
            out[var] = None
            continue
        pct = (s > cfg["norma"]).mean() * 100 if cfg["norma"] is not None else None
        out[var] = {
            "prom": s.mean(),
            "min": s.min(),
            "max": s.max(),
            "max_fecha": df.loc[s.idxmax(), "fecha"],
            "pct_sobre_norma": pct,
            "n": len(s),
        }
    return out


def nivel(var: str, valor: float) -> str:
    cfg = VARIABLES[var]
    if cfg["critico"] is not None and valor >= cfg["critico"]:
        return "🔴"
    if cfg["norma"] is not None and valor > cfg["norma"]:
        return "🟡"
    return "🟢"


def texto_resumen(titulo: str, res: dict) -> str:
    lineas = [f"📊 <b>{titulo}</b>", ""]
    for var, r in res.items():
        cfg = VARIABLES[var]
        if r is None:
            continue
        u = cfg["unidad"]
        lineas.append(f"<b>{cfg['nombre']}</b>")
        lineas.append(f"  Promedio: {r['prom']:.1f} {u}")
        lineas.append(f"  Pico: {r['max']:.1f} {u} ({r['max_fecha']:%d/%m %H:%M})")
        if r["pct_sobre_norma"] is not None:
            lineas.append(f"  Sobre norma ({cfg['norma']} {u}): {r['pct_sobre_norma']:.1f}% de las lecturas")
        lineas.append("")
    return "\n".join(lineas).strip()


def pronostico(df: pd.DataFrame, var: str, horas: int = 6):
    """
    Pronóstico estadístico simple (NO meteorológico): mezcla la tendencia
    reciente amortiguada con el perfil horario promedio de los últimos días.
    Devuelve una Serie indexada por hora futura, o None si faltan datos.
    """
    s = df.set_index("fecha")[var].dropna().resample("1h").mean().dropna()
    if len(s) < 6:
        return None
    ultimo_t = s.index[-1]
    ahora = pd.Timestamp.now(tz=ultimo_t.tz)
    if ahora - ultimo_t > pd.Timedelta(hours=3):
        return None  # datos demasiado viejos

    reciente = s.iloc[-6:]
    pendiente = np.polyfit(np.arange(len(reciente)), reciente.values, 1)[0]
    ultimo = reciente.iloc[-1]
    perfil = s.groupby(s.index.hour).mean()

    valores, fechas = [], []
    for h in range(1, horas + 1):
        t = ultimo_t + pd.Timedelta(hours=h)
        tendencia = ultimo + pendiente * sum(0.7**k for k in range(1, h + 1))
        peso = 0.7**h
        base = perfil.get(t.hour, ultimo)
        valores.append(max(0.0, peso * tendencia + (1 - peso) * base))
        fechas.append(t)
    return pd.Series(valores, index=fechas)
