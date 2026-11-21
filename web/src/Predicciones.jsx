import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS, LinearScale, CategoryScale, PointElement, LineElement, Tooltip, Legend,
} from "chart.js";
import zoomPlugin from "chartjs-plugin-zoom";
import { get } from "./api";
import "./Admin.css";

ChartJS.register(LinearScale, CategoryScale, PointElement, LineElement, Tooltip, Legend, zoomPlugin);

const fecha = (v) =>
  new Date(v).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

const opcionesTiempo = (ejes) => ({
  responsive: true, maintainAspectRatio: false, parsing: false, animation: false,
  scales: {
    x: { 
      type: "linear", 
      ticks: { callback: fecha, maxTicksLimit: 8 }, 
      grid: { display: false }
    },
    ...ejes,
  },
  plugins: { 
    legend: { position: "top", labels: { boxWidth: 12, font: { family: "system-ui", size: 13 } } },
    tooltip: { callbacks: { title: (it) => fecha(it[0].parsed.x) } },
    zoom: {
      pan: { enabled: true, mode: "x" },
      zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: "x" }
    }
  },
});

const puntos = (arr, k) =>
  arr.filter((p) => p[k] != null && p[k] < 300)
     .map((p) => ({ x: Date.parse(p.t), y: p[k] }));

export default function Predicciones() {
  const [predData, setPredData] = useState(null);
  const [error, setError] = useState(null);
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

  useEffect(() => {
    get("/api/publico/predicciones-manana?variable=pm2_5")
      .then((res) => { setPredData(res); setError(null); })
      .catch((e) => setError(e.message));
  }, []);

  if (!predData) return <main className={`pagina admin ${darkMode ? "dark" : ""}`}><div className="cargando">Cargando pronóstico del aire...</div></main>;

  const realPts = puntos(predData.real, "valor");
  
  // Filtramos estrictamente el modelo ganador "rf_v3" para que sea una sola línea limpia
  const predichosGanador = predData.predicho.filter((p) => p.modelo && p.modelo === "rf_v3");
  const ptsPronostico = predichosGanador
    .filter((p) => p.valor != null && p.valor < 300)
    .map((p) => ({ x: Date.parse(p.t), y: p.valor }));

  const datasetsGrafico = [
    {
      label: "PM2.5 real",
      data: realPts,
      borderColor: "#2563eb",
      backgroundColor: "transparent",
      borderWidth: 2.5,
      pointRadius: 0,
      tension: 0.2,
    },
    {
      label: "Predicho (rf_v3)",
      data: ptsPronostico,
      borderColor: "#16a34a",
      backgroundColor: "transparent",
      borderWidth: 3,
      borderDash: [6, 6],
      pointRadius: 0,
      tension: 0.2,
    }
  ];

  return (
    <main className={`pagina admin ${darkMode ? "dark" : ""}`}>
      <div className="barra" style={{ padding: "1.25rem 1.75rem", borderRadius: "16px", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", margin: 0 }}>Pronóstico de Calidad del Aire</h1>
          <p style={{ margin: "0.2rem 0 0 0", color: "var(--text-muted)", fontSize: "0.9rem" }}>Visualización oficial del modelo predictivo</p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button onClick={() => setDarkMode(!darkMode)} className="btn-icono" title="Cambiar modo de vista">
            {darkMode ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>
            )}
          </button>
          <Link to="/" className="btn-accion-header" title="Volver al panel principal" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", textDecoration: "none" }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
            Panel principal
          </Link>
        </div>
      </div>

      <section className="tarjeta" style={{ marginBottom: "1.5rem", background: "linear-gradient(135deg, rgba(37,99,235,0.04), rgba(22,163,74,0.04))" }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span>💡</span> Información del pronóstico
        </h3>
        <p style={{ margin: 0, lineHeight: "1.5", color: "var(--text-muted)", fontSize: "0.95rem" }}>
          Gráfico optimizado con el modelo oficial <b>rf_v3</b>. La línea azul muestra los registros reales y la línea verde discontinua proyecta la estimación ambiental de forma limpia.
        </p>
      </section>

      <div className="contenedor-graficos">
        <section className="tarjeta">
          <h3>PM2.5: real vs. predicho (rf_v3)</h3>
          <div className="grafico" style={{ height: "420px" }}>
            <Line data={{ datasets: datasetsGrafico }} options={opcionesTiempo({
              y: { beginAtZero: true, title: { display: true, text: "µg/m³ (PM2.5)" }, grid: { color: "rgba(0,0,0,0.04)" } },
            })} />
          </div>
        </section>
      </div>
    </main>
  );
}