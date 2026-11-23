"""Script de inferencia para el endpoint de SageMaker (contenedor scikit-learn)."""
import json
import os

import joblib
import pandas as pd


def model_fn(model_dir):
    return joblib.load(os.path.join(model_dir, "model.joblib"))


def input_fn(request_body, content_type="application/json"):
    if content_type != "application/json":
        raise ValueError(f"Content-Type no soportado: {content_type}")
    return pd.DataFrame(json.loads(request_body)["instances"])


def predict_fn(data, model):
    return model.predict_proba(data[["views", "price", "brand", "category"]])[:, 1].tolist()


def output_fn(prediction, accept="application/json"):
    return json.dumps({"scores": prediction}), "application/json"
