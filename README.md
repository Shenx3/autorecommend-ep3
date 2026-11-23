# AutoRecommend AI · EP3

Sistema de recomendación de productos para ShopFast (retail de tecnología, Chile).
Proyecto de la asignatura ITY1102 Arquitectura de Sistemas de Inteligencia Artificial.

**Integrantes:** Bastián Bravo · Nicolás Álvarez

## Qué hace

Predice qué productos de un catálogo tienen mayor probabilidad de comprarse y entrega las mejores recomendaciones a través de una API REST.

```
Cliente / Dashboard ──HTTPS──> nginx ──> API FastAPI ──> Endpoint SageMaker (modelo)
                                            │
                                            └─ POST /events ──> RabbitMQ ──> Consumidor ──> SQLite
                                                                                         (historial del usuario,
                                                                                          lo usa la API al recomendar)
```

| Componente | Tecnología | Dónde corre |
|---|---|---|
| Modelo de propensión de compra | scikit-learn (Random Forest) | Endpoint de **Amazon SageMaker** |
| API REST | FastAPI + Swagger (`/docs`) | EC2 (Docker) |
| Mensajería | RabbitMQ | EC2 (Docker) |
| Dashboard | Streamlit | EC2 (Docker) |
| TLS | nginx con certificado autofirmado | EC2 (Docker) |

> **Versión simplificada:** el diseño de EP1/EP2 propone un modelo Two-Tower con infraestructura completa (ECS, Redis, MWAA, Multi-AZ).
> En EP3 se implementa un modelo más simple y una infraestructura mínima operativa sobre AWS Academy.

## Estructura

```
model/       train.py, inference.py, deploy.py, autoscaling.py, test_endpoint.py, teardown.py
api/         main.py (API), consumer.py (RabbitMQ -> SQLite), Dockerfile
dashboard/   app.py (Streamlit), Dockerfile
nginx/       nginx.conf (TLS y proxy a la API)
tests/       test_unit.py, test_integration.py, locustfile.py
scripts/     gen_cert.sh, setup_ec2.sh
artifacts/   catalog.csv y metrics.json (los genera train.py)
docs/        evidencias: capturas, resultados de Locust
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio |
| GET | `/recommendations/{user_id}?n=10` | Top-N productos (requiere `x-api-key`) |
| POST | `/events` | Publica un evento `view` / `cart` / `purchase` en RabbitMQ (requiere `x-api-key`) |

Documentación interactiva: `https://<IP>/docs`

## Seguridad implementada

- API Key en header `x-api-key`.
- Rate limiting por IP (`RATE_LIMIT`, por defecto 100/minuto → responde 429).
- Validación estricta: `user_id` UUID, `n` entre 1 y 20, tipos de evento permitidos.
- La respuesta no expone scores internos del modelo.
- Fallback a Top Sellers si SageMaker no responde en `SAGEMAKER_TIMEOUT` segundos.
- TLS en nginx (certificado autofirmado) y contenedores sin usuario root.

## Cómo ejecutarlo

### 1. Entrenar y desplegar el modelo (notebook de SageMaker)

```python
%pip install -q "sagemaker<3" scikit-learn==1.2.1      # luego: Kernel > Restart
%run model/train.py --input events.csv
%run model/deploy.py
%run model/test_endpoint.py
```

Descargar `artifacts/catalog.csv` y `artifacts/metrics.json` y guardarlos en este repositorio.

### 2. Levantar el sistema (EC2)

```bash
cp .env.example .env          # editar API_KEY y claves
bash scripts/gen_cert.sh
docker compose up -d --build
```

- API: `https://<IP>/docs`
- Dashboard: `http://<IP>:8501`
- RabbitMQ: `http://<IP>:15672`

### 3. Pruebas

```bash
pip install -r api/requirements.txt -r tests/requirements.txt
pytest tests/test_unit.py -v                                              # unitarias
BASE_URL=https://<IP> API_KEY=<clave> pytest tests/test_integration.py -v # integración
API_KEY=<clave> locust -f tests/locustfile.py --headless -u 50 -r 5 -t 2m --host https://<IP> --csv docs/locust
```

### 4. Apagar recursos

```python
%run model/teardown.py     # borra el endpoint de SageMaker
```

## Declaración de uso de IA

Completar con las herramientas de IA utilizadas, para qué y cómo se verificó el resultado.
