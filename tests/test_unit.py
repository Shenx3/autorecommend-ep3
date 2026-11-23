"""Pruebas unitarias y de componentes de la API (no necesitan AWS ni RabbitMQ).

Ejecutar:  pytest tests/test_unit.py -v
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
KEY = {"x-api-key": "test-key"}


def rec_url(user=None, n=None):
    url = f"/recommendations/{user or uuid.uuid4()}"
    return url + (f"?n={n}" if n is not None else "")


@pytest.fixture
def fake_model(monkeypatch):
    """Simula el endpoint de SageMaker: el ultimo producto del catalogo tiene el mayor score."""
    monkeypatch.setattr(main, "invoke_model", lambda instances: [float(i) for i in range(len(instances))])


def test_01_health_responde_200():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_02_sin_api_key_devuelve_401():
    assert client.get(rec_url()).status_code == 401


def test_03_api_key_incorrecta_devuelve_401():
    assert client.get(rec_url(), headers={"x-api-key": "mala"}).status_code == 401


def test_04_user_id_no_uuid_devuelve_422():
    assert client.get("/recommendations/no-es-uuid", headers=KEY).status_code == 422


def test_05_n_igual_a_cero_devuelve_422():
    assert client.get(rec_url(n=0), headers=KEY).status_code == 422


def test_06_n_mayor_al_maximo_devuelve_422():
    assert client.get(rec_url(n=21), headers=KEY).status_code == 422


def test_07_devuelve_exactamente_n_productos(fake_model):
    r = client.get(rec_url(n=5), headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "model" and len(body["items"]) == 5


def test_08_orden_por_score_del_modelo(fake_model):
    items = client.get(rec_url(n=3), headers=KEY).json()["items"]
    assert [i["product_id"] for i in items] == [1015, 1014, 1013]


def test_09_respuesta_no_expone_scores_internos(fake_model):
    body = client.get(rec_url(), headers=KEY).json()
    assert "score" not in str(body).lower()


def test_10_fallback_top_sellers_si_el_modelo_falla(monkeypatch):
    def caida(instances):
        raise TimeoutError("SageMaker no responde")
    monkeypatch.setattr(main, "invoke_model", caida)
    r = client.get(rec_url(n=4), headers=KEY)
    body = r.json()
    assert r.status_code == 200 and body["source"] == "fallback_top_sellers"
    assert [i["product_id"] for i in body["items"]] == [1001, 1002, 1003, 1004]


def test_11_evento_valido_se_encola(monkeypatch):
    publicados = []
    monkeypatch.setattr(main, "publish_event", publicados.append)
    r = client.post("/events", headers=KEY,
                    json={"user_id": str(uuid.uuid4()), "product_id": 1001, "event_type": "view"})
    assert r.status_code == 202 and r.json() == {"queued": True} and len(publicados) == 1


def test_12_evento_con_tipo_invalido_devuelve_422():
    r = client.post("/events", headers=KEY,
                    json={"user_id": str(uuid.uuid4()), "product_id": 1001, "event_type": "hackeo"})
    assert r.status_code == 422


def test_13_evento_sin_api_key_devuelve_401():
    r = client.post("/events", json={"user_id": str(uuid.uuid4()), "product_id": 1001, "event_type": "view"})
    assert r.status_code == 401


def test_14_cola_caida_devuelve_503(monkeypatch):
    def caida(payload):
        raise ConnectionError("RabbitMQ caido")
    monkeypatch.setattr(main, "publish_event", caida)
    r = client.post("/events", headers=KEY,
                    json={"user_id": str(uuid.uuid4()), "product_id": 1001, "event_type": "view"})
    assert r.status_code == 503
