"""Pruebas de la cache de recomendaciones (no necesitan AWS ni RabbitMQ).

Ejecutar:  pytest tests/test_cache.py -v
"""
import uuid

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
KEY = {"x-api-key": "test-key"}


def modelo_falso(llamadas):
    def fake(instances):
        llamadas.append(1)
        return [float(i) for i in range(len(instances))]
    return fake


def test_15_segunda_consulta_sale_de_la_cache(monkeypatch):
    llamadas = []
    monkeypatch.setattr(main, "invoke_model", modelo_falso(llamadas))
    url = f"/recommendations/{uuid.uuid4()}?n=5"
    r1 = client.get(url, headers=KEY).json()
    r2 = client.get(url, headers=KEY).json()
    assert r1["cache"] == "miss" and r2["cache"] == "hit"
    assert len(llamadas) == 1 and r1["items"] == r2["items"]


def test_16_un_evento_nuevo_invalida_la_cache(monkeypatch):
    llamadas, bought = [], set()
    monkeypatch.setattr(main, "invoke_model", modelo_falso(llamadas))
    monkeypatch.setattr(main, "user_history", lambda uid: ({}, set(bought)))
    url = f"/recommendations/{uuid.uuid4()}?n=3"
    r1 = client.get(url, headers=KEY).json()
    assert r1["items"][0]["product_id"] == 1015
    bought.add(1015)  # llega un evento de compra
    r2 = client.get(url, headers=KEY).json()
    assert r2["cache"] == "miss" and 1015 not in [i["product_id"] for i in r2["items"]]
    assert len(llamadas) == 2


def test_17_el_fallback_no_se_guarda_en_cache(monkeypatch):
    def caida(instances):
        raise TimeoutError("SageMaker no responde")
    monkeypatch.setattr(main, "invoke_model", caida)
    url = f"/recommendations/{uuid.uuid4()}?n=3"
    r1 = client.get(url, headers=KEY).json()
    r2 = client.get(url, headers=KEY).json()
    assert r1["source"] == r2["source"] == "fallback_top_sellers"
    assert r1["cache"] == r2["cache"] == "miss"
