"""
API de telemetria de calidad del aire (FastAPI) -> lee MariaDB (solo lectura).

Publico : /api/publico/estado, /api/publico/serie24h
Admin   : /api/admin/login, /api/admin/serie, /api/admin/nodo, /api/admin/predicciones

python -m uvicorn main:app --app-dir api --reload --port 8000

Todos los timestamps de la base estan en UTC; la API los devuelve en ISO 8601 con 'Z'.
"""
import hashlib
import hmac
import os
import time
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "user": os.getenv("DB_USER"),      # usuario de SOLO LECTURA
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True,
}
NODO_DEFECTO = os.getenv("NODO_DEFECTO", "N01")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "").encode()
TOKEN_HORAS = 8
MINUTOS_VIGENTE = 30            # sin datos por mas de esto -> "datos desactualizados"

# Umbrales (ug/m3, promedio 24 h): (limite_bueno OMS, limite_regular norma Chile)
LIM_PM25 = (15, 50)
LIM_PM10 = (45, 150)

app = FastAPI(title="API Calidad del Aire - Temuco")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- Utilidades ----------
@contextmanager
def db():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn.cursor()
    finally:
        conn.close()


def consultar(sql, params=()):
    with db() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def a_float(v):
    return None if v is None else float(v)


def nivel(valor, limites):
    """0 = Bueno, 1 = Regular, 2 = Malo."""
    if valor is None:
        return None
    if valor <= limites[0]:
        return 0
    return 1 if valor <= limites[1] else 2


CATEGORIAS = [
    ("Bueno", "green", "El aire está limpio. Puedes realizar actividades al aire libre con normalidad."),
    ("Regular", "yellow", "Calidad aceptable. Personas sensibles (niños, adultos mayores, asmáticos) deberían reducir el esfuerzo intenso al aire libre."),
    ("Malo", "red", "Aire contaminado. Evita el ejercicio al aire libre y mantén ventanas cerradas si es posible."),
]


# ---------- Autenticacion simple (token firmado con expiracion) ----------
def crear_token():
    exp = str(int(time.time()) + TOKEN_HORAS * 3600)
    firma = hmac.new(TOKEN_SECRET, exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{firma}"


def token_valido(token):
    try:
        exp, firma = token.split(".", 1)
        esperado = hmac.new(TOKEN_SECRET, exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(firma, esperado) and int(exp) > time.time()
    except (ValueError, AttributeError):
        return False


bearer = HTTPBearer(auto_error=False)


def requiere_admin(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not TOKEN_SECRET or cred is None or not token_valido(cred.credentials):
        raise HTTPException(status_code=401, detail="No autorizado")


class Login(BaseModel):
    password: str


@app.post("/api/admin/login")
def login(datos: Login):
    if not ADMIN_PASSWORD or not TOKEN_SECRET:
        raise HTTPException(status_code=500, detail="Servidor sin credenciales configuradas")
    if not hmac.compare_digest(datos.password, ADMIN_PASSWORD):
        time.sleep(1)                                  # frena fuerza bruta basica
        raise HTTPException(status_code=401, detail="Clave incorrecta")
    return {"token": crear_token(), "expira_horas": TOKEN_HORAS}


# ---------- Consultas compartidas ----------
def serie_bucket(columnas, nodo, horas, bucket_min):
    """Promedios por intervalo. 'columnas' viene de una lista blanca, no del usuario."""
    seg = bucket_min * 60
    selects = ", ".join(f"AVG({c}) AS {c}" for c in columnas)
    sql = f"""
        SELECT DATE_ADD('1970-01-01',
                 INTERVAL (TIMESTAMPDIFF(SECOND,'1970-01-01',timestamp) DIV %s * %s) SECOND) AS t,
               {selects}
        FROM lecturas_raw
        WHERE nodo_id = %s AND timestamp >= UTC_TIMESTAMP() - INTERVAL %s HOUR
        GROUP BY t ORDER BY t"""
    filas = consultar(sql, (seg, seg, nodo, horas))
    return [{"t": iso(f["t"]), **{c: a_float(f[c]) for c in columnas}} for f in filas]


# ---------- Publico ----------
@app.get("/api/publico/estado")
def estado(nodo_id: str = NODO_DEFECTO):
    ult = consultar(
        """SELECT timestamp, pm2_5, pm10, temperatura, humedad,
                  TIMESTAMPDIFF(MINUTE, timestamp, UTC_TIMESTAMP()) AS min_sin_datos
           FROM lecturas_raw WHERE nodo_id = %s ORDER BY id DESC LIMIT 1""", (nodo_id,))
    if not ult:
        raise HTTPException(status_code=404, detail="Sin datos para este nodo")
    ult = ult[0]
    prom = consultar(
        """SELECT AVG(pm2_5) AS pm2_5, AVG(pm10) AS pm10 FROM lecturas_raw
           WHERE nodo_id = %s AND timestamp >= UTC_TIMESTAMP() - INTERVAL 24 HOUR""", (nodo_id,))[0]
    p25, p10 = a_float(prom["pm2_5"]), a_float(prom["pm10"])
    niveles = [n for n in (nivel(p25, LIM_PM25), nivel(p10, LIM_PM10)) if n is not None]
    cat = CATEGORIAS[max(niveles)] if niveles else None
    return {
        "nodo_id": nodo_id,
        "ultima_lectura": iso(ult["timestamp"]),
        "datos_vigentes": ult["min_sin_datos"] <= MINUTOS_VIGENTE,
        "actual": {"pm2_5": ult["pm2_5"], "pm10": ult["pm10"],
                   "temperatura": a_float(ult["temperatura"]), "humedad": a_float(ult["humedad"])},
        "promedio_24h": {"pm2_5": p25, "pm10": p10},
        "categoria": None if cat is None else
            {"nombre": cat[0], "color": cat[1], "recomendacion": cat[2]},
    }


@app.get("/api/publico/serie24h")
def serie24h(nodo_id: str = NODO_DEFECTO):
    return serie_bucket(["pm2_5", "temperatura", "humedad"], nodo_id, 24, 60)


# ---------- Admin ----------
@app.get("/api/admin/serie", dependencies=[Depends(requiere_admin)])
def admin_serie(nodo_id: str = NODO_DEFECTO,
                horas: int = Query(24, ge=1, le=720),
                bucket_min: int = Query(5, ge=1, le=1440)):
    cols = ["pm1_0", "pm2_5", "pm10", "temperatura", "humedad", "presion"]
    return serie_bucket(cols, nodo_id, horas, bucket_min)


@app.get("/api/admin/nodo", dependencies=[Depends(requiere_admin)])
def admin_nodo(nodo_id: str = NODO_DEFECTO):
    filas = consultar(
        """SELECT n.nombre, n.lat, n.lon, m.rssi, m.recibidas, m.corruptas, m.perdidas,
                  ROUND(100 * m.perdidas / NULLIF(m.recibidas + m.perdidas, 0), 2) AS perdida_pct,
                  TIMESTAMPDIFF(MINUTE, m.timestamp, UTC_TIMESTAMP()) AS min_sin_datos,
                  m.timestamp
           FROM nodos n JOIN lecturas_raw m ON m.nodo_id = n.nodo_id
           WHERE n.nodo_id = %s
             AND m.id = (SELECT MAX(id) FROM lecturas_raw WHERE nodo_id = n.nodo_id)""", (nodo_id,))
    if not filas:
        raise HTTPException(status_code=404, detail="Nodo sin datos o no registrado en 'nodos'")
    f = filas[0]
    return {"nodo_id": nodo_id, "nombre": f["nombre"], "lat": float(f["lat"]), "lon": float(f["lon"]),
            "rssi": f["rssi"], "recibidas": f["recibidas"], "corruptas": f["corruptas"],
            "perdidas": f["perdidas"], "perdida_pct": a_float(f["perdida_pct"]),
            "min_sin_datos": f["min_sin_datos"], "ultima_lectura": iso(f["timestamp"])}


@app.get("/api/admin/predicciones", dependencies=[Depends(requiere_admin)])
def admin_predicciones(nodo_id: str = NODO_DEFECTO,
                       variable: str = Query("pm2_5", pattern="^(pm2_5|pm10|temperatura)$"),
                       horas: int = Query(24, ge=1, le=720)):
    real = serie_bucket([variable], nodo_id, horas, 5)
    pred = consultar(
        """SELECT timestamp, valor_predicho FROM predicciones
           WHERE nodo_id = %s AND variable = %s
             AND timestamp >= UTC_TIMESTAMP() - INTERVAL %s HOUR ORDER BY timestamp""",
        (nodo_id, variable, horas))
    return {"variable": variable,
            "real": [{"t": r["t"], "valor": r[variable]} for r in real],
            "predicho": [{"t": iso(p["timestamp"]), "valor": p["valor_predicho"]} for p in pred]}


@app.get("/api/salud")
def salud():
    consultar("SELECT 1")
    return {"ok": True}
