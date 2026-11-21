import asyncio
import logging
from datetime import time, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from tools.alerts_telegram.analisis import nivel, pronostico, resumen, texto_resumen
from tools.alerts_telegram.config import (CHANNEL_ID, COOLDOWN_MIN, DIA_SEMANAL, HORA_DIARIO, HORA_SEMANAL,
                    INTERVALO_ALERTA_S, PERMITIDOS, TOKEN, TZ, VARIABLES, VENTANA_ALERTA_MIN)
from tools.alerts_telegram.db import ahora, leer
from tools.alerts_telegram.graficos import grafico_reporte

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("bot")
HTML = ParseMode.HTML


# ---------- utilidades ----------
def autorizado(func):
    """Si ALLOWED_IDS está definido, solo esos chats/usuarios pueden usar comandos."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if PERMITIDOS:
            ids = {update.effective_chat.id}
            if update.effective_user:
                ids.add(update.effective_user.id)
            if not ids & PERMITIDOS:
                return
        return await func(update, context)
    return wrapper


def _hhmm(valor: str) -> time:
    h, m = valor.split(":")
    return time(int(h), int(m), tzinfo=ZoneInfo(TZ))


async def enviar_reporte(bot, chat_id, df, titulo: str):
    if df.empty:
        await bot.send_message(chat_id, f"⚠️ {titulo}: sin datos en el periodo.")
        return
    texto = texto_resumen(titulo, resumen(df))
    png = await asyncio.to_thread(grafico_reporte, df, titulo)
    if len(texto) <= 1024:
        await bot.send_photo(chat_id, png, caption=texto, parse_mode=HTML)
    else:
        await bot.send_photo(chat_id, png, caption=f"📊 {titulo}")
        await bot.send_message(chat_id, texto, parse_mode=HTML)


# ---------- comandos ----------
@autorizado
async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌿 Monitoreo ambiental\n\n"
        "/estado_actual – valores de los últimos minutos\n"
        "/pronostico – proyección de PM2.5 y PM10 (próximas 6 h)\n"
        "/reporte_hoy – resumen y gráfico del día\n"
    )


@autorizado
async def cmd_estado_actual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = await asyncio.to_thread(leer, ahora() - timedelta(minutes=15))
    if df.empty:
        await update.message.reply_text("⚠️ Sin datos en los últimos 15 minutos.")
        return
    lineas = [f"📡 <b>Estado actual</b> (prom. 15 min, último dato {df['fecha'].max():%H:%M})", ""]
    for var, cfg in VARIABLES.items():
        s = df[var].dropna()
        if s.empty:
            continue
        v = s.mean()
        marca = nivel(var, v) if cfg["norma"] is not None or cfg["critico"] is not None else "•"
        lineas.append(f"{marca} <b>{cfg['nombre']}</b>: {v:.1f} {cfg['unidad']}")
    lineas.append("\n🟢 normal · 🟡 sobre norma · 🔴 nivel crítico")
    await update.message.reply_text("\n".join(lineas), parse_mode=HTML)


@autorizado
async def cmd_reporte_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = ahora()
    inicio = t.replace(hour=0, minute=0, second=0, microsecond=0)
    df = await asyncio.to_thread(leer, inicio)
    await enviar_reporte(context.bot, update.effective_chat.id, df, f"Reporte de hoy ({t:%d/%m/%Y})")


@autorizado
async def cmd_pronostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = await asyncio.to_thread(leer, ahora() - timedelta(days=7))
    lineas = ["🔮 <b>Pronóstico próximas 6 h</b>", ""]
    hay = False
    for var in ("pm25", "pm10"):
        pred = pronostico(df, var) if not df.empty else None
        if pred is None:
            continue
        hay = True
        cfg = VARIABLES[var]
        lineas.append(f"<b>{cfg['nombre']}</b>")
        for t, v in pred.items():
            lineas.append(f"  {t:%H:%M} → {v:.0f} {cfg['unidad']} {nivel(var, v)}")
        lineas.append("")
    if not hay:
        await update.message.reply_text("⚠️ No hay datos recientes suficientes para proyectar.")
        return
    lineas.append("ℹ️ Proyección estadística (tendencia + perfil horario de 7 días), no un modelo meteorológico.")
    await update.message.reply_text("\n".join(lineas), parse_mode=HTML)


# ---------- tareas programadas ----------
async def job_reporte_diario(context: ContextTypes.DEFAULT_TYPE):
    t = ahora()
    df = await asyncio.to_thread(leer, t - timedelta(hours=24), t)
    await enviar_reporte(context.bot, CHANNEL_ID, df, f"Reporte diario – {t:%d/%m/%Y}")


async def job_reporte_semanal(context: ContextTypes.DEFAULT_TYPE):
    t = ahora()
    df = await asyncio.to_thread(leer, t - timedelta(days=7), t)
    await enviar_reporte(context.bot, CHANNEL_ID, df,
                         f"Reporte semanal – {(t - timedelta(days=7)):%d/%m} al {t:%d/%m/%Y}")


async def job_alertas(context: ContextTypes.DEFAULT_TYPE):
    t = ahora()
    df = await asyncio.to_thread(leer, t - timedelta(minutes=VENTANA_ALERTA_MIN))
    if df.empty:
        return
    estado = context.bot_data.setdefault("alertas", {})

    for var, cfg in VARIABLES.items():
        if cfg["critico"] is None:
            continue
        s = df[var].dropna()
        if s.empty:
            continue
        valor = s.mean()
        prev = estado.get(var, {"activa": False, "ultimo": None})

        if valor >= cfg["critico"]:
            repetir = prev["ultimo"] is None or t - prev["ultimo"] > timedelta(minutes=COOLDOWN_MIN)
            if not prev["activa"] or repetir:
                await context.bot.send_message(
                    CHANNEL_ID,
                    f"🚨 <b>ALERTA: {cfg['nombre']} en nivel crítico</b>\n"
                    f"Valor ({VENTANA_ALERTA_MIN} min): <b>{valor:.1f} {cfg['unidad']}</b>\n"
                    f"Umbral crítico: {cfg['critico']} {cfg['unidad']}\n"
                    f"🕒 {t:%d/%m/%Y %H:%M}",
                    parse_mode=HTML,
                )
                estado[var] = {"activa": True, "ultimo": t}
        elif prev["activa"] and valor < cfg["critico"] * 0.9:  # histéresis 10 %
            await context.bot.send_message(
                CHANNEL_ID,
                f"✅ <b>{cfg['nombre']}</b> bajó del umbral crítico: {valor:.1f} {cfg['unidad']}",
                parse_mode=HTML,
            )
            estado[var] = {"activa": False, "ultimo": None}


# ---------- arranque ----------
async def post_init(app: Application):
    await app.bot.set_my_commands([
        ("estado_actual", "Valores actuales"),
        ("pronostico", "Proyección próximas 6 h"),
        ("reporte_hoy", "Resumen y gráfico del día"),
        ("ayuda", "Lista de comandos"),
    ])


def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler(["start", "ayuda"], cmd_ayuda))
    app.add_handler(CommandHandler("estado_actual", cmd_estado_actual))
    app.add_handler(CommandHandler("reporte_hoy", cmd_reporte_hoy))
    app.add_handler(CommandHandler("pronostico", cmd_pronostico))

    jq = app.job_queue
    jq.run_daily(job_reporte_diario, time=_hhmm(HORA_DIARIO), name="reporte_diario")
    jq.run_daily(job_reporte_semanal, time=_hhmm(HORA_SEMANAL), days=(DIA_SEMANAL,), name="reporte_semanal")
    jq.run_repeating(job_alertas, interval=INTERVALO_ALERTA_S, first=10, name="alertas")

    log.info("Bot iniciado")
    app.run_polling()


if __name__ == "__main__":
    main()
