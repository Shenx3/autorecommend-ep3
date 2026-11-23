"""Entrena el modelo de propension de compra (version simplificada del Two-Tower de EP1).

Pregunta que responde el modelo: dado un producto que el usuario vio en una sesion,
¿terminara comprandolo? (clasificacion binaria). Con las probabilidades se ordenan
los productos del catalogo y se recomiendan los mejores.

Uso:
    python train.py --input events.csv
Genera en ../artifacts: model.joblib, metrics.json, catalog.csv
"""
import argparse
import json
import os

import joblib
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

HERE = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True, help="Ruta al events.csv de Kaggle")
parser.add_argument("--rows", type=int, default=1_000_000, help="Maximo de filas a leer")
parser.add_argument("--out", default=os.path.join(HERE, "..", "artifacts"))
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)

# 1. Carga y preparacion -----------------------------------------------------
cols = ["event_type", "product_id", "category_code", "brand", "price", "user_session"]
df = pd.read_csv(args.input, usecols=cols, nrows=args.rows)
df = df[df.event_type.isin(["view", "purchase"])].copy()
df["is_view"] = (df.event_type == "view").astype(int)
df["is_purchase"] = (df.event_type == "purchase").astype(int)

# Una fila por (sesion, producto)
pairs = (
    df.groupby(["user_session", "product_id"])
    .agg(views=("is_view", "sum"), purchases=("is_purchase", "sum"),
         price=("price", "first"), brand=("brand", "first"), category=("category_code", "first"))
    .reset_index()
)
# Solo pares que el usuario vio al menos una vez (evita que "0 vistas" delate la compra)
pairs = pairs[pairs.views >= 1].copy()
pairs["bought"] = (pairs.purchases > 0).astype(int)
pairs["brand"] = pairs.brand.fillna("unknown").astype(str)
pairs["category"] = pairs.category.fillna("unknown").astype(str)
pairs["price"] = pairs.price.fillna(pairs.price.median())

FEATURES = ["views", "price", "brand", "category"]
X, y = pairs[FEATURES], pairs["bought"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

# 2. Modelo ------------------------------------------------------------------
params = dict(n_estimators=100, max_depth=12, min_samples_leaf=5,
              class_weight="balanced", random_state=42, n_jobs=-1)
pre = ColumnTransformer(
    [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), ["brand", "category"])],
    remainder="passthrough",
)
pipe = Pipeline([("pre", pre), ("rf", RandomForestClassifier(**params))]).fit(X_tr, y_tr)

# 3. Evaluacion --------------------------------------------------------------
pred = pipe.predict(X_te)
metrics = {
    "accuracy": float(accuracy_score(y_te, pred)),
    "precision": float(precision_score(y_te, pred, zero_division=0)),
    "recall": float(recall_score(y_te, pred, zero_division=0)),
    "f1": float(f1_score(y_te, pred, zero_division=0)),
}
print("Metricas en test:", json.dumps(metrics, indent=2))

# Orden de columnas tras ColumnTransformer: brand, category, views, price
names = ["brand", "category", "views", "price"]
importances = dict(zip(names, [float(v) for v in pipe.named_steps["rf"].feature_importances_]))

info = {
    "metrics": metrics,
    "params": params,
    "importances": importances,
    "dataset": {
        "events_used": int(len(df)),
        "pairs_total": int(len(pairs)),
        "pairs_train": int(len(X_tr)),
        "pairs_test": int(len(X_te)),
        "purchase_rate": float(y.mean()),
    },
    "sklearn_version": sklearn.__version__,
}

# 4. Artefactos --------------------------------------------------------------
joblib.dump(pipe, os.path.join(args.out, "model.joblib"))
with open(os.path.join(args.out, "metrics.json"), "w") as f:
    json.dump(info, f, indent=2)

catalog = (
    pairs.groupby("product_id")
    .agg(price=("price", "first"), brand=("brand", "first"),
         category=("category", "first"), n_views=("views", "sum"))
    .sort_values("n_views", ascending=False)
    .head(300)
    .reset_index()
)
catalog.to_csv(os.path.join(args.out, "catalog.csv"), index=False)
print(f"Listo. Artefactos guardados en {os.path.abspath(args.out)}")
