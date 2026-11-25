"""AutoRecommend AI - API REST (EP3).

Endpoints:
  GET  /health                      estado del servicio
  GET  /recommendations/{user_id}   top-N productos recomendados (modelo en SageMaker)
  GET  /products                    catalogo de productos candidatos
  POST /events                      publica un evento (view/cart/purchase) en RabbitMQ

Seguridad: API Key (header x-api-key), rate limiting por IP, validacion estricta de
parametros, la respuesta no expone scores internos y hay fallback a Top Sellers.
Optimizacion: cache en memoria con TTL; su clave incluye el historial del usuario,
asi un evento nuevo invalida la entrada automaticamente.
"""
import json
import os
import secrets
import sqlite3
import time
from typing import Literal
from uuid import UUID

import boto3
import pandas as pd
import pika
from botocore.config import Config
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# --- Configuracion (variables de entorno) -----------------------------------
API_KEY = os.environ["API_KEY"]
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT", "autorecommend-endpoint")
SAGEMAKER_TIMEOUT = float(os.getenv("SAGEMAKER_TIMEOUT", "2"))
RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")
CACHE_TTL = float(os.getenv("CACHE_TTL", "60"))  # segundos; 0 desactiva la cache
CACHE_MAX = 5000
RABBIT_HOST = os.getenv("RABBIT_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBIT_USER", "guest")
RABBIT_PASS = os.getenv("RABBIT_PASS", "guest")
ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "/artifacts")
DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "events.db")

# Catalogo de candidatos (ordenado por popularidad: sirve como lista Top Sellers)
CATALOG = pd.read_csv(os.path.join(ARTIFACTS_DIR, "catalog.csv"))
CATALOG["brand"] = CATALOG["brand"].fillna("unknown")
CATALOG["category"] = CATALOG["category"].fillna("unknown")
CATALOG["price"] = CATALOG["price"].fillna(0.0)


def client_ip(request: Request) -> str:
    """IP real del cliente (nginx la envia en X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip)
app = FastAPI(
    title="AutoRecommend AI",
    description="API de recomendacion de productos para ShopFast (EP3).",
    version="1.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def check_key(key: str | None = Depends(api_key_header)) -> None:
    if key is None or not secrets.compare_digest(key, API_KEY):
        raise HTTPException(status_code=401, detail="API Key invalida o ausente")


# --- Cache en memoria con TTL ---------------------------------------------------
_cache: dict[tuple, tuple[float, list[dict]]] = {}


def cache_get(key: tuple) -> list[dict] | None:
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < CACHE_TTL:
        return entry[1]
    _cache.pop(key, None)
    return None


def cache_set(key: tuple, items: list[dict]) -> None:
    if len(_cache) >= CACHE_MAX:
        _cache.clear()
    _cache[key] = (time.monotonic(), items)


# --- Acceso al modelo ---------------------------------------------------------
_runtime = None


def get_runtime():
    global _runtime
    if _runtime is None:
        cfg = Config(read_timeout=SAGEMAKER_TIMEOUT, connect_timeout=SAGEMAKER_TIMEOUT,
                     retries={"max_attempts": 0})
        _runtime = boto3.client("sagemaker-runtime", region_name=AWS_REGION, config=cfg)
    return _runtime


def invoke_model(instances: list[dict]) -> list[float]:
    """Llama al endpoint de SageMaker y devuelve un score por instancia."""
    resp = get_runtime().invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps({"instances": instances}, default=float),
    )
    return json.loads(resp["Body"].read())["scores"]


# --- Historial del usuario (lo escribe el consumidor de RabbitMQ) -------------
def user_history(user_id: str) -> tuple[dict[int, int], set[int]]:
    """Devuelve (vistas por producto, productos ya comprados) del usuario."""
    views: dict[int, int] = {}
    bought: set[int] = set()
    try:
        con = sqlite3.connect(DB_PATH, timeout=1)
        try:
            rows = con.execute(
                "SELECT product_id, event_type, COUNT(*) FROM events "
                "WHERE user_id = ? GROUP BY product_id, event_type", (user_id,),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return views, bought
    for product_id, event_type, count in rows:
        if event_type == "view":
            views[product_id] = count
        elif event_type == "purchase":
            bought.add(product_id)
    return views, bought


# --- Endpoints ------------------------------------------------------------------
@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "catalog_size": int(len(CATALOG))}


@app.get("/recommendations/{user_id}", tags=["Recomendaciones"], dependencies=[Depends(check_key)])
@limiter.limit(RATE_LIMIT)
def recommend(request: Request, user_id: UUID, n: int = Query(10, ge=1, le=20)):
    """Devuelve los `n` productos con mayor probabilidad de compra para el usuario.

    Si el endpoint de SageMaker no responde a tiempo, se entrega la lista Top Sellers.
    El resultado del modelo se guarda en cache; un evento nuevo del usuario la invalida.
    """
    t0 = time.perf_counter()
    uid = str(user_id)
    views, bought = user_history(uid)

    def respond(items: list[dict], source: str, cache: str) -> dict:
        return {
            "user_id": uid,
            "source": source,
            "cache": cache,
            "items": items,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    # La clave incluye el historial: si llega un evento, la clave cambia y se recalcula
    key = (uid, n, tuple(sorted(views.items())), tuple(sorted(bought)))
    if CACHE_TTL > 0:
        cached = cache_get(key)
        if cached is not None:
            return respond(cached, "model", "hit")

    # Postprocesamiento: no recomendar lo que el usuario ya compro
    cand = CATALOG[~CATALOG["product_id"].isin(bought)].copy()
    cand["times_viewed"] = cand["product_id"].map(views).fillna(0).astype(int)
    instances = (
        cand.assign(views=1 + cand["times_viewed"].clip(upper=10))
        [["views", "price", "brand", "category"]].to_dict("records")
    )

    try:
        scores = invoke_model(instances)
        if len(scores) != len(cand):
            raise ValueError("Cantidad de scores inesperada")
        top = cand.assign(score=scores).nlargest(n, "score")
        source = "model"
    except Exception:
        top = cand.head(n)  # catalogo ya viene ordenado por popularidad
        source = "fallback_top_sellers"

    items = [
        {"product_id": int(r.product_id), "brand": r.brand, "category": r.category,
         "price": float(r.price), "times_viewed": int(r.times_viewed)}
        for r in top.itertuples()
    ]
    if source == "model" and CACHE_TTL > 0:
        cache_set(key, items)  # el fallback nunca se guarda
    return respond(items, source, "miss")


@app.get("/products", tags=["Catalogo"], dependencies=[Depends(check_key)])
@limiter.limit(RATE_LIMIT)
def list_products(request: Request, limit: int = Query(300, ge=1, le=300), offset: int = Query(0, ge=0)):
    """Catalogo de productos candidatos (los 300 mas vistos), ordenado por popularidad."""
    page = CATALOG.iloc[offset: offset + limit]
    items = [
        {"product_id": int(r.product_id), "brand": r.brand, "category": r.category, "price": float(r.price)}
        for r in page.itertuples()
    ]
    return {"total": int(len(CATALOG)), "items": items}


class Event(BaseModel):
    user_id: UUID
    product_id: int
    event_type: Literal["view", "cart", "purchase"]


def publish_event(payload: dict) -> None:
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        credentials=pika.PlainCredentials(RABBIT_USER, RABBIT_PASS),
        connection_attempts=3, retry_delay=1, socket_timeout=3,
    )
    conn = pika.BlockingConnection(params)
    try:
        channel = conn.channel()
        channel.queue_declare(queue="events", durable=True)
        channel.basic_publish(
            exchange="", routing_key="events", body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )
    finally:
        conn.close()


@app.post("/events", status_code=202, tags=["Eventos"], dependencies=[Depends(check_key)])
@limiter.limit(RATE_LIMIT)
def post_event(request: Request, event: Event):
    """Publica un evento de usuario en la cola RabbitMQ (se procesa de forma asincrona)."""
    try:
        publish_event(event.model_dump(mode="json"))
    except Exception:
        raise HTTPException(status_code=503, detail="Cola de eventos no disponible")
    return {"queued": True}

@app.get("/products", tags=["Catalogo"], dependencies=[Depends(check_key)])
@limiter.limit(RATE_LIMIT)
def products(request: Request, limit: int = Query(300, ge=1, le=300)):
    """Catálogo de candidatos (ordenado por popularidad). Lo usa la tienda de demostración."""
    items = [
        {"product_id": int(r.product_id), "brand": r.brand, "category": r.category, "price": float(r.price)}
        for r in CATALOG.head(limit).itertuples()
    ]
    return {"total": int(len(CATALOG)), "items": items}