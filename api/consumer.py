"""Consumidor de RabbitMQ: guarda los eventos de la cola 'events' en SQLite.

Asi el flujo queda completo: API -> RabbitMQ -> consumidor -> base de datos -> recomendaciones.
"""
import json
import os
import sqlite3
import time

import pika

RABBIT_HOST = os.getenv("RABBIT_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBIT_USER", "guest")
RABBIT_PASS = os.getenv("RABBIT_PASS", "guest")
DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "events.db")


def connect():
    params = pika.ConnectionParameters(
        host=RABBIT_HOST, credentials=pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    )
    while True:
        try:
            return pika.BlockingConnection(params)
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ no disponible, reintentando en 3 s...", flush=True)
            time.sleep(3)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=5)
    db.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, product_id INTEGER, "
        "event_type TEXT, ts REAL)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id)")
    db.commit()

    channel = connect().channel()
    channel.queue_declare(queue="events", durable=True)
    channel.basic_qos(prefetch_count=10)

    def on_message(ch, method, properties, body):
        try:
            event = json.loads(body)
            db.execute(
                "INSERT INTO events (user_id, product_id, event_type, ts) VALUES (?, ?, ?, ?)",
                (event["user_id"], event["product_id"], event["event_type"], time.time()),
            )
            db.commit()
            ch.basic_ack(method.delivery_tag)
            print("Evento guardado:", event, flush=True)
        except Exception as exc:  # mensaje invalido: se descarta
            print("Evento descartado:", exc, flush=True)
            ch.basic_nack(method.delivery_tag, requeue=False)

    channel.basic_consume(queue="events", on_message_callback=on_message)
    print("Consumidor escuchando la cola 'events'...", flush=True)
    channel.start_consuming()


if __name__ == "__main__":
    main()
