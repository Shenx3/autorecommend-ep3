"""Pruebas de integracion contra el sistema desplegado (API + SageMaker + RabbitMQ).

Ejecutar con la URL real:
    BASE_URL=https://IP_DE_LA_EC2 API_KEY=tu-clave pytest tests/test_integration.py -v
"""
import os
import time
import uuid

import pytest
import requests
import urllib3

urllib3.disable_warnings()  # certificado autofirmado

BASE_URL = os.getenv("BASE_URL")
KEY = {"x-api-key": os.getenv("LIVE_API_KEY", "")}
pytestmark = pytest.mark.skipif(not BASE_URL, reason="Define BASE_URL para correr las pruebas de integracion")


def test_i1_health_en_el_sistema_desplegado():
    assert requests.get(f"{BASE_URL}/health", verify=False, timeout=10).status_code == 200


def test_i2_api_consume_el_endpoint_de_sagemaker():
    r = requests.get(f"{BASE_URL}/recommendations/{uuid.uuid4()}?n=10", headers=KEY, verify=False, timeout=15)
    body = r.json()
    assert r.status_code == 200 and body["source"] == "model" and len(body["items"]) == 10


def test_i3_evento_viaja_por_rabbitmq_y_cambia_la_recomendacion():
    user = str(uuid.uuid4())
    base = requests.get(f"{BASE_URL}/recommendations/{user}?n=20", headers=KEY, verify=False, timeout=15).json()
    product = base["items"][0]["product_id"]
    r = requests.post(f"{BASE_URL}/events", headers=KEY, verify=False, timeout=10,
                      json={"user_id": user, "product_id": product, "event_type": "purchase"})
    assert r.status_code == 202
    time.sleep(3)  # el consumidor procesa la cola
    after = requests.get(f"{BASE_URL}/recommendations/{user}?n=20", headers=KEY, verify=False, timeout=15).json()
    assert product not in [i["product_id"] for i in after["items"]]  # ya lo compro: se excluye
