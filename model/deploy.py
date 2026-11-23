"""Despliega el modelo en un endpoint de SageMaker.

Ejecutar desde un notebook de SageMaker:   %run model/deploy.py
Requisito: haber ejecutado antes train.py (existe ../artifacts/model.joblib)
"""
import os
import tarfile

import boto3
import sagemaker
from sagemaker.sklearn.model import SKLearnModel

HERE = os.path.dirname(os.path.abspath(__file__))
ENDPOINT_NAME = "autorecommend-endpoint"
INSTANCE_TYPE = "ml.t2.medium"  # si el Learner Lab no la permite, prueba ml.m5.large


def get_role():
    try:
        return sagemaker.get_execution_role()
    except Exception:
        return boto3.client("iam").get_role(RoleName="LabRole")["Role"]["Arn"]


tar_path = os.path.join(HERE, "model.tar.gz")
with tarfile.open(tar_path, "w:gz") as tar:
    tar.add(os.path.join(HERE, "..", "artifacts", "model.joblib"), arcname="model.joblib")

session = sagemaker.Session()
model_data = session.upload_data(tar_path, key_prefix="autorecommend")
print("Modelo subido a:", model_data)

model = SKLearnModel(
    model_data=model_data,
    role=get_role(),
    entry_point=os.path.join(HERE, "inference.py"),
    framework_version="1.2-1",
    py_version="py3",
)
model.deploy(
    instance_type=INSTANCE_TYPE,
    initial_instance_count=1,
    endpoint_name=ENDPOINT_NAME,
)
print("Endpoint listo:", ENDPOINT_NAME)
