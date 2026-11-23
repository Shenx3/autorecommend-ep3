"""Prueba rapida del endpoint de SageMaker (sirve de evidencia para el informe)."""
import json
import time

import boto3

runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")
payload = {"instances": [
    {"views": 1, "price": 250.0, "brand": "samsung", "category": "electronics.smartphone"},
    {"views": 3, "price": 80.0, "brand": "unknown", "category": "unknown"},
]}
t0 = time.perf_counter()
resp = runtime.invoke_endpoint(EndpointName="autorecommend-endpoint",
                               ContentType="application/json", Body=json.dumps(payload))
print("Respuesta:", json.loads(resp["Body"].read()))
print(f"Latencia: {(time.perf_counter() - t0) * 1000:.0f} ms")
