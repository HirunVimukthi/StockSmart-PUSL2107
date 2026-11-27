import base64
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "stocksmart.db"
SCHEMA = ROOT / "database" / "schema.sql"

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_engine.routing import calculate_s_shape_route

JWT_SECRET = os.getenv("STOCKSMART_JWT_SECRET", "stocksmart-development-secret-change-me")
JWT_ALGORITHM = "HS256"
FERNET_KEY = os.getenv("FERNET_KEY") or os.getenv("STOCKSMART_FERNET_KEY")
if not FERNET_KEY:
    FERNET_KEY = base64.urlsafe_b64encode(
        hashlib.sha256("stocksmart-development-encryption-key".encode()).digest()
    ).decode()
fernet = Fernet(FERNET_KEY.encode())


def encrypt_supplier_value(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    try:
        fernet.decrypt(value.encode())
        return value
    except InvalidToken:
        return fernet.encrypt(value.encode()).decode()


def decrypt_supplier_value(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supplier contact data could not be decrypted",
        ) from error


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()


def init_database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    accounts = {
        "admin@stocksmart.local": ("Alice Admin", "admin123", "admin"),
        "manager@stocksmart.local": ("Mason Manager", "manager123", "manager"),
        "warehouse@stocksmart.local": ("Wendy Warehouse", "warehouse123", "warehouse"),
        "cashier@stocksmart.local": ("Charlie Cashier", "cashier123", "cashier"),
        "customer@stocksmart.local": ("Casey Customer", "customer123", "customer"),
    }
    for email, (full_name, password, role) in accounts.items():
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        connection.execute(
            """
            INSERT INTO users (full_name, email, password_hash, role, is_locked)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(email) DO UPDATE SET
                full_name=excluded.full_name,
                password_hash=excluded.password_hash,
                role=excluded.role
            """,
            (full_name, email, password_hash, role),
        )

    seed_suppliers = [
        (1, "GreenFields Dairy", "+1-555-0101", "orders@greenfields.example"),
        (2, "Harvest Bread Co.", "+1-555-0102", "supply@harvest.example"),
        (3, "Prime Produce Wholesale", "+1-555-0103", "trade@primeproduce.example"),
        (4, "Global Pantry Distributors", "+1-555-0104", "quotes@globalpantry.example"),
    ]
    for supplier_id, name, contact, email in seed_suppliers:
        supplier = connection.execute(
            "SELECT contact_encrypted, email FROM suppliers WHERE id=?",
            (supplier_id,),
        ).fetchone()
        if supplier is None:
            connection.execute(
                """
                INSERT INTO suppliers (id, name, contact_encrypted, email)
                VALUES (?, ?, ?, ?)
                """,
                (
                    supplier_id,
                    name,
                    encrypt_supplier_value(contact),
                    encrypt_supplier_value(email),
                ),
            )
            continue

        stored_contact = supplier[0]
        if stored_contact in (None, "", "ENCRYPTED_AT_STARTUP"):
            stored_contact = contact
        stored_email = supplier[1] or email
        connection.execute(
            """
            UPDATE suppliers
            SET contact_encrypted=?, email=?
            WHERE id=?
            """,
            (
                encrypt_supplier_value(stored_contact),
                encrypt_supplier_value(stored_email),
                supplier_id,
            ),
        )
    existing_suppliers = connection.execute(
        "SELECT id, contact_encrypted, email FROM suppliers"
    ).fetchall()
    for supplier in existing_suppliers:
        connection.execute(
            """
            UPDATE suppliers
            SET contact_encrypted=?, email=?
            WHERE id=?
            """,
            (
                encrypt_supplier_value(supplier[1]),
                encrypt_supplier_value(supplier[2]),
                supplier[0],
            ),
        )
    connection.execute(
        """
        INSERT OR IGNORE INTO purchase_quotes
            (id, sku, supplier_id, requested_qty, status)
        VALUES (1, 'RCE-500', 4, 30, 'pending')
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO purchase_quotes
            (id, sku, supplier_id, requested_qty, status)
        VALUES (2, 'EGG-012', 1, 24, 'approved')
        """
    )
    connection.commit()
    connection.close()


init_database()

app = FastAPI(title="StockSmart API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


class LoginRequest(BaseModel):
    email: str
    password: str


class ProductRequest(BaseModel):
    sku: str
    name: str
    category: str
    stock_qty: int = Field(ge=0)
    reorder_threshold: int = Field(ge=0)
    shelf_location: str
    unit_price: float = Field(gt=0)


class CheckoutItem(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    customer_id: Optional[int] = None
    items: list[CheckoutItem]


class StockAdjustRequest(BaseModel):
    sku: str
    qty_change: int
    reason: str = "manual adjustment"


class QuoteRequest(BaseModel):
    sku: str
    supplier_id: int
    requested_qty: int = Field(gt=0)

class OrderCreateRequest(BaseModel):
    customer_id: Optional[int] = None
    order_type: str = "online"
    items: list[CheckoutItem]


class OrderStatusUpdateRequest(BaseModel):
    status: str


def create_token(user_id: int, role: str):
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        user_id = int(payload["sub"])
        role = payload["role"]
    except (JWTError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {"id": user_id, "role": role}


def require_roles(*allowed_roles: str):
    def guard(user=Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role permissions")
        return user

    return guard


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "StockSmart"}


@app.post("/api/login")
def login(request: LoginRequest, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM users WHERE email=?", (request.email.strip().lower(),)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if row["is_locked"] == 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is locked")
    if not bcrypt.checkpw(request.password.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_token(row["id"], row["role"])
    return {"token": token, "role": row["role"], "full_name": row["full_name"], "user_id": row["id"]}


@app.get("/api/admin/users")
def list_users(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    rows = db.execute(
        "SELECT id, email, role, is_locked FROM users ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/admin/users/{user_id}/toggle-lock")
def toggle_user_lock(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    if user["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot lock or unlock their own account",
        )
    target = db.execute(
        "SELECT id, is_locked FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_locked = 0 if target["is_locked"] == 1 else 1
    action = "user locked" if is_locked else "user unlocked"
    db.execute("UPDATE users SET is_locked=? WHERE id=?", (is_locked, user_id))
    db.execute(
        "INSERT INTO audit_logs (user_id, action, flagged_anomaly) VALUES (?, ?, 0)",
        (user["id"], action),
    )
    db.commit()
    return {"id": user_id, "is_locked": is_locked}


@app.get("/api/products")
def list_products(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM products ORDER BY category, name").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/suppliers")
def list_suppliers(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager")),
):
    rows = db.execute(
        "SELECT id, name, contact_encrypted, email FROM suppliers ORDER BY name"
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "contact": decrypt_supplier_value(row["contact_encrypted"]),
            "email": decrypt_supplier_value(row["email"]),
        }
        for row in rows
    ]


@app.post("/api/products")
def add_or_update_product(
    product: ProductRequest,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager")),
):
    db.execute(
        """
        INSERT INTO products (sku, name, category, stock_qty, reorder_threshold, shelf_location, unit_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sku) DO UPDATE SET
            name=excluded.name,
            category=excluded.category,
            stock_qty=excluded.stock_qty,
            reorder_threshold=excluded.reorder_threshold,
            shelf_location=excluded.shelf_location,
            unit_price=excluded.unit_price
        """,
        (
            product.sku.upper(),
            product.name,
            product.category,
            product.stock_qty,
            product.reorder_threshold,
            product.shelf_location.upper(),
            product.unit_price,
        ),
    )
    db.commit()
    db.execute(
        "INSERT INTO audit_logs (user_id, action, sku, qty_change, flagged_anomaly) VALUES (?, ?, ?, 0, 0)",
        (user["id"], "product upsert", product.sku.upper()),
    )
    db.commit()
    return {"success": True, "sku": product.sku.upper()}


@app.post("/api/pos/checkout")
def checkout(
    request: CheckoutRequest,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "cashier")),
):
    if not request.items:
        raise HTTPException(status_code=400, detail="Checkout must contain at least one item")

    total = 0.0
    checked_items = []
    for item in request.items:
        product = db.execute("SELECT * FROM products WHERE sku=?", (item.sku.upper(),)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail=f"Unknown SKU: {item.sku}")
        if product["stock_qty"] < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {item.sku}")
        total += product["unit_price"] * item.quantity
        checked_items.append((product, item.quantity))

    cursor = db.execute(
        "INSERT INTO orders (customer_id, order_type, status, total_amount) VALUES (?, 'sale', 'paid', ?)",
        (request.customer_id, total),
    )
    order_id = cursor.lastrowid

    for product, quantity in checked_items:
        db.execute(
            "INSERT INTO order_items (order_id, sku, quantity) VALUES (?, ?, ?)",
            (order_id, product["sku"], quantity),
        )
        new_stock = product["stock_qty"] - quantity
        db.execute("UPDATE products SET stock_qty=? WHERE sku=?", (new_stock, product["sku"]))
        db.execute(
            "INSERT INTO audit_logs (user_id, action, sku, qty_change, flagged_anomaly) VALUES (?, 'pos checkout', ?, ?, 0)",
            (user["id"], product["sku"], -quantity),
        )
        if new_stock < product["reorder_threshold"]:
            supplier = db.execute("SELECT id FROM suppliers ORDER BY id LIMIT 1").fetchone()
            if supplier:
                db.execute(
                    """
                    INSERT INTO purchase_quotes (sku, supplier_id, requested_qty, status)
                    SELECT ?, ?, ?, 'pending'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM purchase_quotes
                        WHERE sku=? AND status='pending'
                    )
                    """,
                    (
                        product["sku"],
                        supplier["id"],
                        max(product["reorder_threshold"] * 2 - new_stock, 1),
                        product["sku"],
                    ),
                )
    db.commit()
    return {"order_id": order_id, "status": "paid", "total_amount": round(total, 2)}


@app.get("/api/orders/pick-route/{order_id}")
def pick_route(
    order_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager", "warehouse")),
):
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    rows = db.execute(
        """
        SELECT oi.sku, oi.quantity, p.name, p.shelf_location
        FROM order_items oi
        JOIN products p ON p.sku=oi.sku
        WHERE oi.order_id=?
        """,
        (order_id,),
    ).fetchall()
    optimized = calculate_s_shape_route([dict(row) for row in rows])
    return {
        "order_id": order_id,
        "status": order["status"],
        **optimized,
    }


@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(
    request: OrderCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager", "warehouse", "cashier", "customer")),
):
    if not request.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    customer_id = user["id"] if user["role"] == "customer" else request.customer_id
    total = 0.0
    checked_items = []

    for item in request.items:
        product = db.execute("SELECT * FROM products WHERE sku=?", (item.sku.upper(),)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail=f"Unknown SKU: {item.sku}")
        if product["stock_qty"] < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {item.sku}")
        total += product["unit_price"] * item.quantity
        checked_items.append((product, item.quantity))

    cursor = db.execute(
        "INSERT INTO orders (customer_id, order_type, status, total_amount) VALUES (?, ?, 'pending', ?)",
        (customer_id, request.order_type.strip().lower(), total),
    )
    order_id = cursor.lastrowid

    for product, quantity in checked_items:
        db.execute(
            "INSERT INTO order_items (order_id, sku, quantity) VALUES (?, ?, ?)",
            (order_id, product["sku"], quantity),
        )
        new_stock = product["stock_qty"] - quantity
        db.execute("UPDATE products SET stock_qty=? WHERE sku=?", (new_stock, product["sku"]))
        db.execute(
            "INSERT INTO audit_logs (user_id, action, sku, qty_change, flagged_anomaly) VALUES (?, 'order created', ?, ?, 0)",
            (user["id"], product["sku"], -quantity),
        )
        if new_stock < product["reorder_threshold"]:
            supplier = db.execute("SELECT id FROM suppliers ORDER BY id LIMIT 1").fetchone()
            if supplier:
                db.execute(
                    """
                    INSERT INTO purchase_quotes (sku, supplier_id, requested_qty, status)
                    SELECT ?, ?, ?, 'pending'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM purchase_quotes
                        WHERE sku=? AND status='pending'
                    )
                    """,
                    (
                        product["sku"],
                        supplier["id"],
                        max(product["reorder_threshold"] * 2 - new_stock, 1),
                        product["sku"],
                    ),
                )

    db.commit()
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "order_type": request.order_type.strip().lower(),
        "status": "pending",
        "total_amount": round(total, 2),
    }


@app.get("/api/orders")
def list_orders(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager", "warehouse", "cashier", "customer")),
):
    if user["role"] == "customer":
        rows = db.execute(
            "SELECT * FROM orders WHERE customer_id=? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


@app.patch("/api/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    request: OrderStatusUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager", "warehouse")),
):
    new_status = request.status.strip().lower()
    if new_status not in VALID_ORDER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(sorted(VALID_ORDER_STATUSES))}",
        )

    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    db.execute(
        "INSERT INTO audit_logs (user_id, action, flagged_anomaly) VALUES (?, ?, 0)",
        (user["id"], f"order #{order_id} status -> {new_status}"),
    )
    db.commit()
    return {"order_id": order_id, "status": new_status}

@app.post("/api/stock/adjust")
def adjust_stock(
    adjustment: StockAdjustRequest,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager", "warehouse")),
):
    product = db.execute("SELECT * FROM products WHERE sku=?", (adjustment.sku.upper(),)).fetchone()
    if not product:
        raise HTTPException(status_code=404, detail="SKU not found")
    new_stock = product["stock_qty"] + adjustment.qty_change
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    flagged = adjustment.qty_change < -20
    db.execute("UPDATE products SET stock_qty=? WHERE sku=?", (new_stock, adjustment.sku.upper()))
    db.execute(
        "INSERT INTO audit_logs (user_id, action, sku, qty_change, flagged_anomaly) VALUES (?, ?, ?, ?, ?)",
        (user["id"], adjustment.reason, adjustment.sku.upper(), adjustment.qty_change, int(flagged)),
    )
    db.commit()
    return {"sku": adjustment.sku.upper(), "stock_qty": new_stock, "flagged_anomaly": flagged}


@app.get("/api/quotes")
def list_quotes(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager")),
):
    rows = db.execute(
        """
        SELECT q.*, s.name AS supplier_name
        FROM purchase_quotes q
        JOIN suppliers s ON s.id=q.supplier_id
        ORDER BY q.created_at DESC, q.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/quotes/{quote_id}/approve")
def approve_quote(
    quote_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin", "manager")),
):
    quote = db.execute("SELECT * FROM purchase_quotes WHERE id=?", (quote_id,)).fetchone()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    db.execute("UPDATE purchase_quotes SET status='approved' WHERE id=?", (quote_id,))
    db.execute(
        "INSERT INTO audit_logs (user_id, action, sku, qty_change, flagged_anomaly) VALUES (?, 'purchase quote approved', ?, 0, 0)",
        (user["id"], quote["sku"]),
    )
    db.commit()
    return {"id": quote_id, "status": "approved"}


@app.get("/api/security/alerts")
def security_alerts(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    rows = db.execute(
        """
        SELECT a.*, u.full_name, u.email
        FROM audit_logs a
        LEFT JOIN users u ON u.id=a.user_id
        WHERE a.flagged_anomaly=1
        ORDER BY a.timestamp DESC, a.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
