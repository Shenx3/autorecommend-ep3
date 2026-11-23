"""Borra el endpoint, su configuracion y el modelo para no gastar presupuesto del Learner Lab."""
import boto3

sm = boto3.client("sagemaker", region_name="us-east-1")
NAME = "autorecommend-endpoint"
for step, call in [
    ("endpoint", lambda: sm.delete_endpoint(EndpointName=NAME)),
    ("endpoint config", lambda: sm.delete_endpoint_config(EndpointConfigName=NAME)),
]:
    try:
        call()
        print("Borrado:", step)
    except Exception as exc:
        print("No se pudo borrar", step, "->", exc)

# El modelo tiene un nombre generado: se borran los que usan el prefijo del SDK
for m in sm.list_models(NameContains="sagemaker-scikit-learn")["Models"]:
    sm.delete_model(ModelName=m["ModelName"])
    print("Modelo borrado:", m["ModelName"])
