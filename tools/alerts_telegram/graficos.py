import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import seaborn as sns

from tools.alerts_telegram.config import TZ, VARIABLES


def grafico_reporte(df, titulo: str) -> io.BytesIO:
    """PNG de alta resolución: material particulado (con normas) + temp/humedad."""
    sns.set_theme(style="whitegrid", context="talk")

    span = df["fecha"].max() - df["fecha"].min()
    regla = "10min" if span.days < 2 else "1h"
    d = df.set_index("fecha")[list(VARIABLES)].resample(regla).mean()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})

    colores = {"pm1": "#4c9be8", "pm25": "#e8744c", "pm10": "#7a5195"}
    for var, c in colores.items():
        ax1.plot(d.index, d[var], label=VARIABLES[var]["nombre"], color=c, linewidth=2)
        norma = VARIABLES[var]["norma"]
        if norma is not None:
            ax1.axhline(norma, color=c, linestyle="--", alpha=0.6, linewidth=1.2,
                        label=f"Norma {VARIABLES[var]['nombre']} ({norma})")
    ax1.set_ylabel("µg/m³")
    ax1.set_title(titulo, fontweight="bold")
    ax1.legend(ncol=3, fontsize=11, loc="upper left")

    ax2.plot(d.index, d["temp"], color="#d9534f", linewidth=2, label="Temperatura (°C)")
    ax2.set_ylabel("°C", color="#d9534f")
    ax3 = ax2.twinx()
    ax3.plot(d.index, d["hum"], color="#337ab7", linewidth=2, label="Humedad (%)")
    ax3.set_ylabel("%", color="#337ab7")
    ax3.grid(False)

    fmt = "%H:%M" if span.days < 2 else "%d/%m"
    ax2.xaxis.set_major_formatter(mdates.DateFormatter(fmt, tz=d.index.tz))
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    buf.seek(0)
    return buf
