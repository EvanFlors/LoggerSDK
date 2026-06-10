import json
import sys
import pika

def main() -> None:
    conn = pika.BlockingConnection(pika.URLParameters("amqp://guest:guest@localhost/"))
    ch = conn.channel()
    ch.exchange_declare(exchange="logs", exchange_type="fanout", durable=True)
    ch.queue_declare(queue="logs", durable=True)
    ch.queue_bind(queue="logs", exchange="logs")
    for method, _props, body in ch.consume("logs", inactivity_timeout=1):
        if method is None:
            continue
        try:
            print(json.loads(body), flush=True)
        except Exception:
            print(body.decode("utf-8", "replace"), flush=True)
        ch.basic_ack(method.delivery_tag)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
