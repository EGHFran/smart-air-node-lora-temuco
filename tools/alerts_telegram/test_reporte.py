"""Fuerza ahora el reporte diario al canal (sin esperar a las 08:00)."""
import asyncio
from datetime import timedelta

from telegram import Bot

from tools.alerts_telegram.bot import enviar_reporte
from tools.alerts_telegram.config import CHANNEL_ID, TOKEN
from tools.alerts_telegram.db import ahora, leer


async def main():
    t = ahora()
    df = leer(t - timedelta(hours=24), t)
    print(f"{len(df)} filas en las últimas 24 h")
    async with Bot(TOKEN) as bot:
        await enviar_reporte(bot, CHANNEL_ID, df, "Prueba de reporte diario")
    print("Enviado al canal")


asyncio.run(main())
