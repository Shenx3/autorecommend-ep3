"""Prueba de carga con Locust.

Ejemplo (sin interfaz web, 50 usuarios, 2 minutos):
  API_KEY=tu-clave locust -f tests/locustfile.py --headless -u 50 -r 5 -t 2m \
      --host https://IP_DE_LA_EC2 --csv docs/locust
Genera docs/locust_stats.csv con p50, p95, p99, throughput y tasa de errores.
IMPORTANTE: sube RATE_LIMIT en el .env (ej. 100000/minute) antes de la prueba.
"""
import os
import random
import uuid

from locust import HttpUser, between, task

KEY = {"x-api-key": os.getenv("API_KEY", "")}
USERS = [str(uuid.uuid4()) for _ in range(200)]


class ShopUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.client.verify = False  # certificado autofirmado

    @task(5)
    def recomendaciones(self):
        self.client.get(f"/recommendations/{random.choice(USERS)}?n=10", headers=KEY,
                        name="/recommendations/{user_id}")

    @task(1)
    def evento(self):
        self.client.post("/events", headers=KEY, name="/events", json={
            "user_id": random.choice(USERS),
            "product_id": random.randint(1, 1000),
            "event_type": random.choice(["view", "view", "cart", "purchase"]),
        })
