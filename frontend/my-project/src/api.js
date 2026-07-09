const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export async function sendMessage(dashboardOwner, message) {
  const res = await fetch(`${API_BASE}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dashboard_owner: dashboardOwner, message }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Request failed (${res.status}): ${text}`);
  }

  return res.json();
}