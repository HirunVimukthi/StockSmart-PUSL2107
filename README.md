# StockSmart

StockSmart is a starter enterprise inventory, POS, purchasing, and audit application built with FastAPI, SQLite, Scikit-Learn, and vanilla HTML/CSS/JavaScript.

## Project structure

- `backend/` - FastAPI application and JWT/RBAC authorization
- `database/` - SQL schema and seed data
- `ai_engine/` - standalone 7-day demand forecasting script
- `frontend/` - role-based browser pages
- `stocksmart.db` - SQLite database, created automatically at first backend start

## Setup

1. Install Python 3.10 or newer.
2. From the repository root, create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   py -m pip install -r requirements.txt
   ```

4. Start the API:

   ```powershell
   py -m uvicorn backend.main:app --reload
   ```

   The API documentation is available at `http://127.0.0.1:8000/docs`.

5. In a second terminal, serve the frontend:

   ```powershell
   py -m http.server 5500 --directory frontend
   ```

   Open `http://127.0.0.1:5500/login.html`.

The backend executes `database/schema.sql` automatically when imported. Supplier contact values are encrypted with Fernet. Set `STOCKSMART_FERNET_KEY` and `STOCKSMART_JWT_SECRET` in a local `.env` or process environment for deployment.

## Test accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@stocksmart.local | admin123 |
| Manager | manager@stocksmart.local | manager123 |
| Warehouse | warehouse@stocksmart.local | warehouse123 |
| Cashier | cashier@stocksmart.local | cashier123 |
| Customer | customer@stocksmart.local | customer123 |

## Demand forecasting

The forecasting script creates sample historical sales data on its first run and prints a 7-day prediction for every SKU:

```powershell
py ai_engine/forecast.py
```

## Key API examples

- `POST /api/login`
- `GET /api/products`
- `POST /api/pos/checkout`
- `GET /api/orders/pick-route/{order_id}`
- `POST /api/stock/adjust`
- `GET /api/quotes`
- `POST /api/quotes/{id}/approve`
- `GET /api/security/alerts`