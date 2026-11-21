const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export const getToken = () => sessionStorage.getItem("token");
export const setToken = (t) => (t ? sessionStorage.setItem("token", t) : sessionStorage.removeItem("token"));

export async function get(path) {
  const token = getToken();
  const r = await fetch(BASE + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

export async function login(password) {
  const r = await fetch(BASE + "/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!r.ok) throw new Error("Clave incorrecta");
  setToken((await r.json()).token);
}
