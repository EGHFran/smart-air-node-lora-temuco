import { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, Tooltip, Legend, Filler,
} from "chart.js";
import { get } from "./api";
import "./App.css";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

const NIVELES = [
  { nombre: "Bueno", color: "green", texto: "PM2.5 hasta 15 µg/m³ (límite OMS)" },
  { nombre: "Regular", color: "yellow", texto: "PM2.5 entre 15 y 50 µg/m³ (límite norma chilena)" },
  { nombre: "Malo", color: "red", texto: "PM2.5 sobre 50 µg/m³" },
];

const hora = (t) =>
  new Date(t).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });

function Dato({ etiqueta, valor, unidad }) {
  return (
    <div className="dato">
      <span className="dato-valor">{valor ?? "—"}<small> {valor != null && unidad}</small></span>
      <span className="dato-etiqueta">{etiqueta}</span>
    </div>
  );
}

export default function App() {
  const [estado, setEstado] = useState(null);
  const [serie, setSerie] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    const cargar = () =>
      Promise.all([get("/api/publico/estado"), get("/api/publico/serie24h")])
        .then(([e, s]) => { setEstado(e); setSerie(s); setError(null); })
        .catch((e) => setError(e.message));
    cargar();
    const id = setInterval(cargar, 60000);
    return () => clearInterval(id);
  }, []);

  if (error && !estado) return <main className="pagina"><p className="aviso">No se pudo cargar la información ({error}).</p></main>;
  if (!estado) return <main className="pagina"><p>Cargando…</p></main>;

  const cat = estado.categoria;
  const grafico = {
    labels: serie.map((p) => hora(p.t)),
    datasets: [
      { label: "PM2.5 (µg/m³)", data: serie.map((p) => p.pm2_5), borderColor: "#2563eb",
        backgroundColor: "rgba(37,99,235,.12)", fill: true, tension: 0.3, yAxisID: "y" },
      { label: "Temperatura (°C)", data: serie.map((p) => p.temperatura), borderColor: "#ea580c",
        tension: 0.3, yAxisID: "y1" },
    ],
  };
  const opciones = {
    responsive: true, maintainAspectRatio: false,
    scales: {
      y: { position: "left", beginAtZero: true, title: { display: true, text: "µg/m³" } },
      y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "°C" } },
    },
  };

  return (
    <main className="pagina">
      <header>
        <h1>Calidad del aire en Temuco</h1>
        <p className="sub">Última lectura: {estado.ultima_lectura ? new Date(estado.ultima_lectura).toLocaleString("es-CL") : "—"}</p>
      </header>

      {!estado.datos_vigentes && (
        <p className="aviso">⚠ El sensor no ha enviado datos recientemente. Los valores pueden estar desactualizados.</p>
      )}

      {cat && (
        <section className={`estado ${cat.color}`}>
          <p className="estado-etiqueta">Estado del aire (promedio 24 h)</p>
          <h2>{cat.nombre}</h2>
          <p>{cat.recomendacion}</p>
        </section>
      )}

      <section className="datos">
        <Dato etiqueta="PM2.5 ahora" valor={estado.actual.pm2_5} unidad="µg/m³" />
        <Dato etiqueta="PM10 ahora" valor={estado.actual.pm10} unidad="µg/m³" />
        <Dato etiqueta="Temperatura" valor={estado.actual.temperatura?.toFixed(1)} unidad="°C" />
        <Dato etiqueta="Humedad" valor={estado.actual.humedad?.toFixed(0)} unidad="%" />
      </section>

      <section className="tarjeta">
        <h3>Últimas 24 horas</h3>
        <div className="grafico"><Line data={grafico} options={opciones} /></div>
      </section>

      <section className="tarjeta">
        <h3>¿Qué significan los niveles?</h3>
        <ul className="niveles">
          {NIVELES.map((n) => (
            <li key={n.nombre}><span className={`punto ${n.color}`} /><b>{n.nombre}:</b> {n.texto}</li>
          ))}
        </ul>
        <p className="nota">PM2.5 son partículas muy finas que pueden llegar a los pulmones. Fuente: sensor propio, referencias OMS 2021 y norma chilena.</p>
      </section>
    </main>
  );
}
