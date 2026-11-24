const API_BASE = "http://127.0.0.1:8000";

function token() {
  return localStorage.getItem("stocksmart_token");
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}

function requireRole(roles) {
  const role = localStorage.getItem("stocksmart_role");
  if (!token() || !roles.includes(role)) {
    window.location.href = "login.html";
  }
}

function logout() {
  localStorage.clear();
  window.location.href = "login.html";
}

function shell(title, role) {
  document.write(`
    <div class="topbar">
      <div class="brand">StockSmart</div>
      <div><span>${role}</span> <button class="secondary" onclick="logout()">Logout</button></div>
    </div>
    <main class="container"><h1>${title}</h1><slot></slot></main>
  `);
}
