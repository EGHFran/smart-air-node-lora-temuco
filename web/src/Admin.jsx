import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Line, Bar } from "react-chartjs-2";
import {
  Chart as ChartJS, LinearScale, CategoryScale, BarElement, PointElement, LineElement, Tooltip, Legend,
} from "chart.js";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { get, login, getToken, setToken } from "./api";
import "./Admin.css";

ChartJS.register(LinearScale, CategoryScale, BarElement, PointElement, LineElement, Tooltip, Legend);

const RANGOS = [
  { txt: "6 h", horas: 6, bucket: 5 },
  { txt: "24 h", horas: 24, bucket: 5 },
  { txt: "3 días", horas: 72, bucket: 15 },
  { txt: "7 días", horas: 168, bucket: 60 },
];
const fecha = (v) =>
  new Date(v).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const CANALES = [
  ["f1_415nm", "415 nm", "#7c3aed"], ["f2_445nm", "445 nm", "#2563eb"], ["f3_480nm", "480 nm", "#0ea5e9"],
  ["f4_515nm", "515 nm", "#16a34a"], ["f5_555nm", "555 nm", "#84cc16"], ["f6_590nm", "590 nm", "#eab308"],
  ["f7_630nm", "630 nm", "#f97316"], ["f8_680nm", "680 nm", "#dc2626"],
];
const COLORES = { verde: "#16a34a", amarillo: "#ca8a04", rojo: "#dc2626" };

function Gauge({ titulo, valor, max, lims }) {
  const R = 80, cx = 100, cy = 100;
  const ang = (v) => Math.PI * (1 - Math.min(v, max) / max);
  const pt = (v, r = R) => [cx + r * Math.cos(ang(v)), cy - r * Math.sin(ang(v))];
  const arco = (a, b, color) => {
    const [x1, y1] = pt(a), [x2, y2] = pt(b);
    return <path d={`M${x1} ${y1} A${R} ${R} 0 0 1 ${x2} ${y2}`} stroke={color} strokeWidth="16" fill="none" />;
  };
  const [nx, ny] = pt(valor ?? 0, R - 22);
  const col = valor == null ? "#6b7280" : valor <= lims[0] ? COLORES.verde : valor <= lims[1] ? COLORES.amarillo : COLORES.rojo;
  return (
    <div className="gauge">
      <h3>{titulo}</h3>
      <svg viewBox="0 0 200 125">
        {arco(0, lims[0], COLORES.verde)}{arco(lims[0], lims[1], COLORES.amarillo)}{arco(lims[1], max, COLORES.rojo)}
        {valor != null && <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#111827" strokeWidth="3" />}
        <circle cx={cx} cy={cy} r="5" fill="#111827" />
        <text x={cx} y={cy + 20} textAnchor="middle" fontSize="18" fontWeight="700" fill={col}>
          {valor != null ? valor.toFixed(1) : "—"} µg/m³
        </text>
      </svg>
      <small>Verde ≤ {lims[0]} (OMS) · Amarillo ≤ {lims[1]} (Chile)</small>
    </div>
  );
}

function Mapa({ nodo }) {
  const div = useRef(null);
  useEffect(() => {
    if (!nodo) return;
    const mapa = L.map(div.current).setView([nodo.lat, nodo.lon], 15);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap",
    }).addTo(mapa);
    const r = nodo.rssi;
    const color = r == null ? "#6b7280" : r > -90 ? COLORES.verde : r > -110 ? COLORES.amarillo : COLORES.rojo;
    L.circleMarker([nodo.lat, nodo.lon], { radius: 12, color, fillColor: color, fillOpacity: 0.8 })
      .addTo(mapa).bindPopup(`${nodo.nombre}<br>RSSI: ${r} dBm`);
    return () => mapa.remove();
  }, [nodo]);
  return <div ref={div} className="mapa" />;
}

const opcionesTiempo = (ejes) => ({
  responsive: true, maintainAspectRatio: false, parsing: false, animation: false,
  scales: {
    x: { type: "linear", ticks: { callback: fecha, maxTicksLimit: 7 } },
    ...ejes,
  },
  plugins: { tooltip: { callbacks: { title: (it) => fecha(it[0].parsed.x) } } },
});
const puntos = (arr, k) =>
  arr.filter((p) => p[k] != null).map((p) => ({ x: Date.parse(p.t), y: p[k] }));
const linea = (label, data, color, eje = "y") =>
  ({ label, data, borderColor: color, backgroundColor: color, pointRadius: 0, borderWidth: 2, tension: 0.2, yAxisID: eje });

function Panel({ salir }) {
  const [rango, setRango] = useState(RANGOS[1]);
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const cargar = () =>
      Promise.all([
        get("/api/admin/nodo"), get("/api/publico/estado"),
        get(`/api/admin/serie?horas=${rango.horas}&bucket_min=${rango.bucket}`),
        get(`/api/admin/predicciones?variable=pm2_5&horas=${rango.horas}`),
        get(`/api/admin/espectro?horas=${rango.horas}&bucket_min=${rango.bucket * 3}`)
          .catch(() => ({ serie: [], ultimo: null })),
      ]).then(([nodo, estado, serie, pred, esp]) => { setD({ nodo, estado, serie, pred, esp }); setError(null); })
        .catch((e) => (e.message === "401" ? salir() : setError(e.message)));
    cargar();
    const id = setInterval(cargar, 60000);
    return () => clearInterval(id);
  }, [rango]);

  if (!d) return <p>{error ? `Error: ${error}` : "Cargando…"}</p>;
  const { nodo, estado, serie, pred, esp } = d;
  const pm = estado.promedio_24h;
  const dsMet = [
    linea("PM1.0", puntos(serie, "pm1_0"), "#93c5fd"), linea("PM2.5", puntos(serie, "pm2_5"), "#2563eb"),
    linea("PM10", puntos(serie, "pm10"), "#1e3a8a"),
    linea("Temperatura (°C)", puntos(serie, "temperatura"), "#ea580c", "y1"),
    linea("Humedad (%)", puntos(serie, "humedad"), "#0d9488", "y1"),
  ];
  const dsPred = [
    linea("PM2.5 real", pred.real.map((p) => ({ x: Date.parse(p.t), y: p.valor })).filter((p) => p.y != null), "#2563eb"),
    { ...linea("PM2.5 predicho (ML)", pred.predicho.map((p) => ({ x: Date.parse(p.t), y: p.valor })), "#ea580c"), borderDash: [8, 6] },
  ];
  const dsEsp = [
    ...CANALES.map(([k, l, c]) => linea(l, puntos(esp.serie, k), c)),
    linea("Clear", puntos(esp.serie, "clear_ch"), "#6b7280", "y1"),
    linea("NIR", puntos(esp.serie, "nir"), "#7f1d1d", "y1"),
  ];
  const barras = {
    labels: CANALES.map((c) => c[1]),
    datasets: [{ data: CANALES.map((c) => esp.ultimo?.[c[0]] ?? null), backgroundColor: CANALES.map((c) => c[2]) }],
  };
  const rssiColor = nodo.rssi > -90 ? "green" : nodo.rssi > -110 ? "yellow" : "red";

  return (
    <>
      <div className="barra">
        {RANGOS.map((r) => (
          <button key={r.txt} className={r === rango ? "activo" : ""} onClick={() => setRango(r)}>{r.txt}</button>
        ))}
      </div>
      {nodo.min_sin_datos > 30 && <p className="aviso">⚠ Nodo sin datos hace {nodo.min_sin_datos} min.</p>}

      <section className="gauges">
        <Gauge titulo="PM2.5 promedio 24 h" valor={pm.pm2_5} max={100} lims={[15, 50]} />
        <Gauge titulo="PM10 promedio 24 h" valor={pm.pm10} max={200} lims={[45, 150]} />
      </section>

      {estado.horas_cubiertas_24h < 23.5 && (
        <p className="aviso">ℹ Los promedios de 24 h se calculan con solo {estado.horas_cubiertas_24h} h de datos.</p>
      )}

      <section className="datos">
        <div className="dato"><span className="dato-valor">{nodo.horas_datos}<small> h</small></span><span className="dato-etiqueta">Datos disponibles ({nodo.total_lecturas} lecturas, desde {nodo.primera_lectura ? fecha(nodo.primera_lectura) : "—"})</span></div>
        <div className="dato"><span className="dato-valor">{nodo.rssi ?? "—"}<small> dBm</small></span><span className="dato-etiqueta">RSSI ({rssiColor === "green" ? "bueno" : rssiColor === "yellow" ? "débil" : "crítico"})</span></div>
        <div className="dato"><span className="dato-valor">{nodo.perdida_pct ?? "—"}<small> %</small></span><span className="dato-etiqueta">Pérdida acumulada</span></div>
        <div className="dato"><span className="dato-valor">{nodo.min_sin_datos}<small> min</small></span><span className="dato-etiqueta">Sin datos</span></div>
        <div className="dato"><span className="dato-valor">{nodo.recibidas}<small> / {nodo.corruptas} / {nodo.perdidas}</small></span><span className="dato-etiqueta">Recibidas / corruptas / perdidas</span></div>
      </section>

      <div className="dos">
        <section className="tarjeta">
          <h3>Meteorología vs. material particulado</h3>
          <div className="grafico"><Line data={{ datasets: dsMet }} options={opcionesTiempo({
            y: { position: "left", beginAtZero: true, title: { display: true, text: "µg/m³" } },
            y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "°C / %" } },
          })} /></div>
        </section>
        <section className="tarjeta">
          <h3>{nodo.nombre}</h3>
          <Mapa nodo={nodo} />
        </section>
      </div>

      <div className="dos">
        <section className="tarjeta">
          <h3>Espectro (AS7341) en el tiempo</h3>
          {esp.serie.length === 0 && <p className="nota">Sin lecturas de espectro en este rango.</p>}
          <div className="grafico"><Line data={{ datasets: dsEsp }} options={opcionesTiempo({
            y: { position: "left", beginAtZero: true, title: { display: true, text: "Cuentas (F1–F8)" } },
            y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Clear / NIR" } },
          })} /></div>
        </section>
        <section className="tarjeta">
          <h3>Última lectura por canal</h3>
          <p className="nota">{esp.ultimo ? fecha(esp.ultimo.t) : "Sin datos"}</p>
          <div className="grafico"><Bar data={barras} options={{ responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }} /></div>
          {esp.ultimo && <p className="nota">Clear: {esp.ultimo.clear_ch} · NIR: {esp.ultimo.nir}</p>}
        </section>
      </div>

      <section className="tarjeta">
        <h3>PM2.5: real vs. predicho por ML</h3>
        {pred.predicho.length === 0 && <p className="nota">Aún no hay predicciones registradas.</p>}
        <div className="grafico"><Line data={{ datasets: dsPred }} options={opcionesTiempo({
          y: { beginAtZero: true, title: { display: true, text: "µg/m³" } },
        })} /></div>
      </section>
    </>
  );
}

function Login({ onOk }) {
  const [clave, setClave] = useState("");
  const [err, setErr] = useState(null);
  const enviar = async (e) => {
    e.preventDefault();
    try { await login(clave); onOk(); } catch (x) { setErr(x.message); }
  };
  return (
    <form className="login" onSubmit={enviar}>
      <h2>Panel de administrador</h2>
      <input type="password" placeholder="Clave" value={clave} onChange={(e) => setClave(e.target.value)} autoFocus />
      <button type="submit">Entrar</button>
      {err && <span className="aviso">{err}</span>}
      <Link to="/">← Panel ciudadano</Link>
    </form>
  );
}

export default function Admin() {
  const [auth, setAuth] = useState(!!getToken());
  const salir = () => { setToken(null); setAuth(false); };
  if (!auth) return <Login onOk={() => setAuth(true)} />;
  return (
    <main className="pagina admin">
      <div className="barra">
        <h1>Panel de administrador</h1>
        <Link to="/">Panel ciudadano</Link>
        <button onClick={salir}>Cerrar sesión</button>
      </div>
      <Panel salir={salir} />
    </main>
  );
}
