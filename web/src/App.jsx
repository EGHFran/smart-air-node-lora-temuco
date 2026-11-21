import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, Tooltip, Legend, Filler,
} from "chart.js";
import zoomPlugin from "chartjs-plugin-zoom";
import { get } from "./api";
import "./App.css";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler, zoomPlugin);

const NIVELES = [
  { nombre: "Bueno", color: "green", icono: "●", texto: "El aire está limpio. Ideal para realizar actividades al aire libre con total tranquilidad." },
  { nombre: "Regular", color: "yellow", icono: "●", texto: "Calidad aceptable. Personas muy sensibles deberían moderar esfuerzos prolongados al aire libre." },
  { nombre: "Malo", color: "red", icono: "●", texto: "Riesgoso para la salud. Se recomienda evitar actividades físicas intensas al aire libre." },
];

const hora = (t) =>
  new Date(t).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });

function DatoPrincipal({ etiqueta, valor, unidad, descripcion }) {
  return (
    <div className="tarjeta-dato-principal">
      <span className="etiqueta">{etiqueta}</span>
      <div className="valor-container">
        <span className="valor">{valor ?? "—"}</span>
        <span className="unidad">{valor != null && unidad}</span>
      </div>
      {descripcion && <span className="descripcion">{descripcion}</span>}
    </div>
  );
}

export default function App() {
  const [estado, setEstado] = useState(null);
  const [serie, setSerie] = useState([]);
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
    const cargar = () =>
      Promise.all([get("/api/publico/estado"), get("/api/publico/serie24h")])
        .then(([e, s]) => { setEstado(e); setSerie(s); setError(null); })
        .catch((e) => setError(e.message));
    cargar();
    const id = setInterval(cargar, 60000);
    return () => clearInterval(id);
  }, []);

  if (error && !estado) return <main className="pagina"><div className="alerta-error">No se pudo cargar la información climática ({error}).</div></main>;
  if (!estado) return <main className="pagina"><div className="cargando">Actualizando información del aire...</div></main>;

  const cat = estado.categoria;
  const grafico = {
    labels: serie.map((p) => hora(p.t)),
    datasets: [
      {
        label: "PM2.5 (µg/m³)",
        data: serie.map((p) => p.pm2_5),
        borderColor: "#2563eb",
        backgroundColor: "rgba(37,99,235,0.08)",
        fill: true,
        tension: 0.35,
        pointRadius: 0,
        borderWidth: 3,
        yAxisID: "y"
      },
      {
        label: "Temperatura (°C)",
        data: serie.map((p) => p.temperatura),
        borderColor: "#ea580c",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.35,
        yAxisID: "y1"
      },
    ],
  };

  const opciones = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "top", labels: { boxWidth: 12, font: { family: "system-ui", size: 13 } } },
      zoom: {
        pan: { enabled: true, mode: "x" },
        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: "x" }
      }
    },
    scales: {
      x: { grid: { display: false } },
      y: { position: "left", beginAtZero: true, title: { display: true, text: "PM2.5 (µg/m³)" }, grid: { color: "rgba(0,0,0,0.04)" } },
      y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Temp (°C)" } },
    },
  };

  return (
    <main className="pagina-ciudadana">
      {/* Cabecera optimizada con iconos profesionales */}
      <header className="header-ciudadano">
        <div className="header-info">
          <h1>Aire Temuco</h1>
          <p className="subtitulo">Monitoreo ciudadano en tiempo real</p>
        </div>
        <div className="header-acciones">
          <Link
            to="/predicciones"
            className="btn-accion-header"
            title="Ver predicciones de aire para mañana"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h5"></path><path d="M17 12h5"></path><path d="M12 2v5"></path><path d="M12 17v5"></path><path d="m4.93 4.93 3.54 3.54"></path><path d="m15.53 15.53 3.54 3.54"></path><path d="m4.93 19.07 3.54-3.54"></path><path d="m15.53 8.47 3.54-3.54"></path></svg>
            Predicciones
          </Link>
          <a
            href="https://t.me/AireTmco_PC"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-accion-header telegram"
            title="Únete al canal de Telegram"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4Z"></path><path d="M22 2 11 13"></path></svg>
            Telegram
          </a>
          <button onClick={() => setDarkMode(!darkMode)} className="btn-icono" title="Cambiar modo de vista">
            {darkMode ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>
            )}
          </button>
          <Link to="/admin" className="btn-accion-header admin" title="Panel de administración">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            Admin
          </Link>
        </div>
      </header>

      {/* Aviso de datos obsoletos si aplica */}
      {!estado.datos_vigentes && (
        <div className="aviso-banner">
          <span>⚠️</span> El sensor se encuentra inactivo temporalmente. Los valores mostrados corresponden a la última lectura registrada.
        </div>
      )}

      {/* Tarjeta principal del Estado del Aire */}
      {cat && (
        <section className={`banner-estado ${cat.color}`}>
          <div className="estado-badge">Estado del aire actual (Promedio 24h)</div>
          <h2>{cat.nombre}</h2>
          <p>{cat.recomendacion}</p>
        </section>
      )}

      {/* Métricas clave */}
      <section className="grilla-datos">
        <DatoPrincipal etiqueta="Material Part Fino (PM2.5)" valor={estado.actual.pm2_5} unidad="µg/m³" descripcion="Partículas respirables finas" />
        <DatoPrincipal etiqueta="Material Particulado (PM10)" valor={estado.actual.pm10} unidad="µg/m³" descripcion="Polvo y cenizas en suspensión" />
        <DatoPrincipal etiqueta="Temperatura Ambiental" valor={estado.actual.temperatura?.toFixed(1)} unidad="°C" descripcion="Condición exterior actual" />
        <DatoPrincipal etiqueta="Humedad Relativa" valor={estado.actual.humedad?.toFixed(0)} unidad="%" descripcion="Saturación de humedad en aire" />
      </section>

      {/* Bloque de Gráfico principal con zoom y desplazamiento */}
      <section className="tarjeta-seccion">
        <div className="tarjeta-header">
          <h3>Evolución de las últimas 24 horas</h3>
          <span className="actualizacion-txt">Actualizado: {estado.ultima_lectura ? new Date(estado.ultima_lectura).toLocaleTimeString("es-CL", { hour: '2-digit', minute: '2-digit' }) : "—"}</span>
        </div>
        <div className="contenedor-grafico-grande">
          <Line data={grafico} options={opciones} />
        </div>
      </section>

      {/* Sección educativa */}
      <section className="tarjeta-seccion educativa">
        <h3>¿Qué significan estos niveles para tu salud?</h3>
        <div className="lista-niveles">
          {NIVELES.map((n) => (
            <div key={n.nombre} className="nivel-item">
              <span className={`nivel-icono-punto ${n.color}`}>{n.icono}</span>
              <div>
                <b>{n.nombre}:</b> <p>{n.texto}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="fuente-info">
          📊 Referencias basadas en normativas de la OMS y Norma Primaria de Calidad del Aire en Chile.
        </div>
      </section>
    </main>
  );
}