"""Dashboard de AutoRecommend AI (Streamlit)."""
import json
import os
import sqlite3
import uuid

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://api:8000")
API_KEY = os.getenv("API_KEY", "")
ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "/artifacts")
DB_PATH = os.path.join(os.getenv("DATA_DIR", "/data"), "events.db")
HEADERS = {"x-api-key": API_KEY}

st.set_page_config(page_title="AutoRecommend AI", layout="wide")
st.title("AutoRecommend AI · Panel de recomendaciones")
st.caption("Recomendador de productos para ShopFast, con el modelo desplegado en Amazon SageMaker.")


@st.cache_data
def load_json(name):
    path = os.path.join(ARTIFACTS_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


@st.cache_data
def load_catalog():
    path = os.path.join(ARTIFACTS_DIR, "catalog.csv")
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=["product_id"])


info = load_json("metrics.json")
catalog = load_catalog()

tab_rec, tab_model, tab_events = st.tabs(["Recomendaciones", "Modelo e interpretabilidad", "Eventos (RabbitMQ)"])

# --- Pestaña 1: recomendaciones ---------------------------------------------
with tab_rec:
    if "uid" not in st.session_state:
        st.session_state.uid = str(uuid.uuid4())
    c1, c2, c3 = st.columns([4, 1, 1])
    uid = c1.text_input("user_id (UUID)", key="uid")
    n = c2.number_input("Cantidad", min_value=1, max_value=20, value=10)
    c3.write("")
    c3.button("UUID nuevo", on_click=lambda: st.session_state.update(uid=str(uuid.uuid4())))

    if st.button("Obtener recomendaciones", type="primary"):
        try:
            r = requests.get(f"{API_URL}/recommendations/{uid}", params={"n": int(n)},
                             headers=HEADERS, timeout=10)
        except requests.RequestException as exc:
            st.error(f"No se pudo contactar la API: {exc}")
        else:
            if r.status_code == 200:
                data = r.json()
                m1, m2 = st.columns(2)
                m1.metric("Latencia de la API (ms)", data["latency_ms"])
                m2.metric("Origen de la respuesta", data["source"])
                if data["source"] != "model":
                    st.warning("El modelo no respondió a tiempo: se entregó la lista Top Sellers (fallback).")
                st.dataframe(pd.DataFrame(data["items"]), use_container_width=True, hide_index=True)
                st.caption(
                    "times_viewed = veces que este usuario vio el producto (eventos recibidos por RabbitMQ). "
                    "Los productos ya comprados por el usuario se excluyen."
                )
            else:
                st.error(f"Error {r.status_code}: {r.text}")

# --- Pestaña 2: modelo ----------------------------------------------------------
with tab_model:
    if not info:
        st.info("Aún no hay metrics.json en artifacts/. Ejecuta model/train.py primero.")
    else:
        st.subheader("Métricas del modelo (conjunto de prueba)")
        cols = st.columns(4)
        for col, key in zip(cols, ["accuracy", "precision", "recall", "f1"]):
            col.metric(key.capitalize() if key != "f1" else "F1-score", f"{info['metrics'][key]:.3f}")

        st.subheader("Interpretabilidad: ¿qué variables pesan más en la decisión?")
        imp = pd.Series(info["importances"]).sort_values(ascending=False)
        st.bar_chart(imp)
        top2 = imp.index[:2].tolist()
        st.write(
            f"El modelo se apoya sobre todo en **{top2[0]}** ({imp.iloc[0]:.0%}) y **{top2[1]}** "
            f"({imp.iloc[1]:.0%}). Esto permite al equipo comercial entender por qué se destacan "
            "ciertos productos y alinear las promociones con las recomendaciones."
        )
        with st.expander("Datos de entrenamiento e hiperparámetros"):
            st.json({"dataset": info["dataset"], "hiperparametros": info["params"]})

# --- Pestaña 3: eventos -------------------------------------------------------
with tab_events:
    st.subheader("Enviar un evento")
    e1, e2, e3 = st.columns(3)
    e_user = e1.text_input("user_id del evento", value=st.session_state.get("uid", str(uuid.uuid4())))
    product_ids = catalog["product_id"].tolist() or [0]
    e_product = e2.selectbox("Producto", product_ids)
    e_type = e3.selectbox("Tipo", ["view", "cart", "purchase"])
    if st.button("Publicar en RabbitMQ"):
        try:
            r = requests.post(f"{API_URL}/events", headers=HEADERS, timeout=10,
                              json={"user_id": e_user, "product_id": int(e_product), "event_type": e_type})
            if r.status_code == 202:
                st.success("Evento publicado en la cola. El consumidor lo guardará en segundos.")
            else:
                st.error(f"Error {r.status_code}: {r.text}")
        except requests.RequestException as exc:
            st.error(f"No se pudo contactar la API: {exc}")

    st.subheader("Últimos eventos procesados por el consumidor")
    if st.button("Actualizar"):
        st.cache_data.clear()
    try:
        con = sqlite3.connect(DB_PATH, timeout=2)
        total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        df = pd.read_sql_query(
            "SELECT user_id, product_id, event_type, datetime(ts,'unixepoch') AS fecha_utc "
            "FROM events ORDER BY id DESC LIMIT 20", con)
        con.close()
        st.metric("Eventos almacenados", total)
        st.dataframe(df, use_container_width=True, hide_index=True)
    except sqlite3.Error:
        st.info("Todavía no hay eventos almacenados.")
