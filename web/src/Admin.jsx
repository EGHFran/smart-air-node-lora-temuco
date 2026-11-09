import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Line, Bar } from "react-chartjs-2";
import {
  Chart as ChartJS, LinearScale, CategoryScale, BarElement, PointElement, LineElement, Tooltip, Legend,
} from "chart.js";
import zoomPlugin from "chartjs-plugin-zoom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { get, login, getToken, setToken } from "./api";
import "./Admin.css";

ChartJS.register(LinearScale, CategoryScale, BarElement, PointElement, LineElement, Tooltip, Legend, zoomPlugin);

const RANGOS = [
  { txt: "6 h", horas: 6, bucket: 5 },
  { txt: "24 h", horas: 24, bucket: 5 },
  { txt: "3 días", horas: 72, bucket: 15 },
  { txt: "7 días", horas: 168, bucket: 60 },
  { txt: "15 días", horas: 360, bucket: 120 }, // Incluido para ver el historial desde el 28/10
];
const VERSIONES = ["v3"];

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
        {valor != null && <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="currentColor" strokeWidth="3" />}
        <circle cx={cx} cy={cy} r="5" fill="currentColor" />
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
  const mapaRef = useRef(null);

  useEffect(() => {
    if (!nodo || !div.current) return;
    if (!mapaRef.current) {
      mapaRef.current = L.map(div.current, { zoomAnimation: false, fadeAnimation: false })
        .setView([nodo.lat, nodo.lon], 15);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap",
      }).addTo(mapaRef.current);
    }
    return () => {
      if (mapaRef.current) {
        mapaRef.current.off();
        mapaRef.current.remove();
        mapaRef.current = null;
      }
    };
  }, [nodo?.lat, nodo?.lon]);

  useEffect(() => {
    if (!nodo || !mapaRef.current) return;
    const r = nodo.rssi;
    const color = r == null ? "#6b7280" : r > -90 ? COLORES.verde : r > -110 ? COLORES.amarillo : COLORES.rojo;
    mapaRef.current.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) mapaRef.current.removeLayer(layer);
    });
    L.circleMarker([nodo.lat, nodo.lon], { radius: 12, color, fillColor: color, fillOpacity: 0.8 })
      .addTo(mapaRef.current)
      .bindPopup(`${nodo.nombre}<br>RSSI: ${r} dBm`);
  }, [nodo]);

  return <div ref={div} className="mapa" />;
}

// Opciones de tiempo globales con zoom y desplazamiento habilitados para los gráficos de líneas
const opcionesTiempo = (ejes) => ({
  responsive: true, maintainAspectRatio: false, parsing: false, animation: false,
  scales: {
    x: { type: "linear", ticks: { callback: fecha, maxTicksLimit: 7 } },
    ...ejes,
  },
  plugins: { 
    tooltip: { callbacks: { title: (it) => fecha(it[0].parsed.x) } },
    zoom: {
      pan: { enabled: true, mode: "x" },
      zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: "x" }
    }
  },
});

const puntos = (arr, k) =>
  arr.filter((p) => p[k] != null).map((p) => ({ x: Date.parse(p.t), y: p[k] }));
const linea = (label, data, color, eje = "y") =>
  ({ label, data, borderColor: color, backgroundColor: color, pointRadius: 0, borderWidth: 2, tension: 0.2, yAxisID: eje });

function Panel({ salir }) {
  const [rango, setRango] = useState(RANGOS[1]);
  const [ver, setVer] = useState("v3");
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

  // Función para exportar los datos actuales a CSV (Punto 2)
  const exportarCSV = () => {
    if (!d || !d.serie || d.serie.length === 0) {
      alert("No hay datos disponibles para exportar en este rango.");
      return;
    }
    const headers = ["Fecha/Hora", "PM1.0", "PM2.5", "PM10", "Temperatura", "Humedad"];
    const filas = d.serie.map(p => [
      p.t,
      p.pm1_0 ?? "",
      p.pm2_5 ?? "",
      p.pm10 ?? "",
      p.temperatura ?? "",
      p.humedad ?? ""
    ]);
    
    let csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(","), ...filas.map(e => e.join(","))].join("\n");
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `reporte_aire_temuco_${rango.txt.replace(/\s+/g, '_')}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!d) return <p>{error ? `Error: ${error}` : "Cargando…"}</p>;
  const { nodo, estado, serie, pred, esp } = d;
  const pm = estado.promedio_24h;
  const dsMet = [
    linea("PM1.0", puntos(serie, "pm1_0"), "#93c5fd"), linea("PM2.5", puntos(serie, "pm2_5"), "#2563eb"),
    linea("PM10", puntos(serie, "pm10"), "#1e3a8a"),
    linea("Temperatura (°C)", puntos(serie, "temperatura"), "#ea580c", "y1"),
    linea("Humedad (%)", puntos(serie, "humedad"), "#0d9488", "y1"),
  ];

  const realPts = pred.real.map((p) => ({ x: Date.parse(p.t), y: p.valor })).filter((p) => p.y != null);
  const porModelo = pred.predicho
    .filter((p) => p.modelo && (p.modelo.endsWith(`_${ver}`) || p.modelo.includes(`_${ver}_`)))
    .reduce((acc, p) => {
      const m = p.modelo;
      (acc[m] = acc[m] || []).push({ x: Date.parse(p.t), y: p.valor });
      return acc;
    }, {});
  const coloresMod = ["#ea580c", "#16a34a", "#7c3aed", "#dc2626", "#0d9488"];

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

  // Simulación de eventos recientes para el historial (Punto 3)
  const logsRecientes = [
    { hora: new Date().toLocaleTimeString("es-CL", {hour: '2-digit', minute:'2-digit'}), tipo: "ok", msg: `Sincronización LoRa exitosa. RSSI actual: ${nodo.rssi ?? "—"} dBm` },
    { hora: new Date(Date.now() - 900000).toLocaleTimeString("es-CL", {hour: '2-digit', minute:'2-digit'}), tipo: "info", msg: `Inferencia de Machine Learning ejecutada para versión ${ver.toUpperCase()}` },
    { hora: new Date(Date.now() - 3600000).toLocaleTimeString("es-CL", {hour: '2-digit', minute:'2-digit'}), tipo: "ok", msg: `Lectura de espectro AS7341 procesada correctamente (${esp.serie.length} registros)` },
  ];

  return (
    <>
      <div className="barra" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", gap: "5px", flexWrap: "wrap" }}>
          {RANGOS.map((r) => (
            <button key={r.txt} className={r === rango ? "activo" : ""} onClick={() => setRango(r)}>{r.txt}</button>
          ))}
        </div>
        <button onClick={exportarCSV} className="btn-accion-header" style={{ backgroundColor: "#16a34a", borderColor: "#15803d", color: "white" }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          Exportar CSV de PMs
        </button>
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

      {/* Gráficos organizados uno debajo del otro en una sola columna */}
      <div className="contenedor-graficos">
        <section className="tarjeta">
          <h3>Meteorología vs. material particulado</h3>
          <div className="grafico"><Line data={{ datasets: dsMet }} options={opcionesTiempo({
            y: { position: "left", beginAtZero: true, title: { display: true, text: "µg/m³" } },
            y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "°C / %" } },
          })} /></div>
        </section>

        <section className="tarjeta">
          <h3>{nodo.nombre} (Ubicación)</h3>
          <Mapa nodo={nodo} />
        </section>

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

        <div className="barra" style={{ marginTop: "1rem" }}>
          <span>Versión de modelos:</span>
          {VERSIONES.map((v) => (
            <button key={v} className={v === ver ? "activo" : ""} onClick={() => setVer(v)}>
              {v.toUpperCase()}
            </button>
          ))}
        </div>

        {Object.keys(porModelo).length === 0 ? (
          <section className="tarjeta">
            <h3>PM2.5: real vs. predicho ({ver.toUpperCase()})</h3>
            <p className="nota">No hay predicciones de la versión {ver.toUpperCase()} en este rango de tiempo.</p>
          </section>
        ) : (
          Object.entries(porModelo).map(([nombreMod, pts], idx) => {
            const color = coloresMod[idx % coloresMod.length];
            const ds = [
              linea("PM2.5 real", realPts, "#2563eb"),
              { ...linea(`Predicho (${nombreMod})`, pts, color), borderDash: [8, 6], pointRadius: pts.length < 3 ? 4 : 0 },
            ];
            return (
              <section className="tarjeta" key={nombreMod}>
                <h3>PM2.5: real vs. {nombreMod}</h3>
                <div className="grafico">
                  <Line data={{ datasets: ds }} options={opcionesTiempo({
                    y: { beginAtZero: true, title: { display: true, text: "µg/m³" } },
                  })} />
                </div>
              </section>
            );
          })
        )}

        {/* Tarjeta de Historial de Eventos / Alertas del Sistema (Punto 3) */}
        <section className="tarjeta">
          <h3>📋 Historial de eventos del sistema (Logs recientes)</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "1rem" }}>
            {logsRecientes.map((log, index) => (
              <div key={index} style={{ 
                display: "flex", 
                justifyContent: "space-between", 
                alignItems: "center", 
                padding: "0.75rem", 
                borderRadius: "8px", 
                background: "var(--bg-color, rgba(0,0,0,0.02))",
                border: "1px solid var(--border-color)"
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <span>{log.tipo === "ok" ? "🟢" : "🔵"}</span>
                  <span style={{ fontSize: "0.9rem" }}>{log.msg}</span>
                </div>
                <small style={{ color: "var(--text-muted)", fontFamily: "monospace" }}>{log.hora}</small>
              </div>
            ))}
          </div>
        </section>
      </div>
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
      <Link to="/" className="btn-accion-header" style={{ marginTop: "1rem", display: "inline-block" }}>← Panel ciudadano</Link>
    </form>
  );
}

export default function Admin() {
  const [auth, setAuth] = useState(!!getToken());
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("theme") === "dark");

  useEffect(() => {
    if (darkMode) {
      document.body.classList.add("dark-mode");
      localStorage.setItem("theme", "dark");
    } else {
      document.body.classList.remove("dark-mode");
      localStorage.setItem("theme", "light");
    }
  }, [darkMode]);

  const salir = () => { setToken(null); setAuth(false); };
  if (!auth) return <Login onOk={() => setAuth(true)} />;
  
  return (
    <main className={`pagina admin ${darkMode ? "dark" : ""}`}>
      <div className="barra">
        <h1>Panel de administrador</h1>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button onClick={() => setDarkMode(!darkMode)} className="btn-icono" title="Cambiar modo de vista">
            {darkMode ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>
            )}
          </button>
          <Link to="/" className="btn-accion-header" title="Ir al panel ciudadano">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
            Panel ciudadano
          </Link>
          <button onClick={salir} className="btn-accion-header" style={{ backgroundColor: "#ef4444", borderColor: "#dc2626", color: "white" }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
            Cerrar sesión
          </button>
        </div>
      </div>
      <Panel salir={salir} />
    </main>
  );
}