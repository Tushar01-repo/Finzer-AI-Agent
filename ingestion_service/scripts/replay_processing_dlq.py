import json

import pika

from app.config.settings import settings


DLQ = "article.processing.dlq"
TARGET_QUEUE = "article.processing"


def main():
    connection = pika.BlockingConnection(
        pika.URLParameters(settings.RABBITMQ_URL)
    )

    channel = connection.channel()

    channel.queue_declare(
        queue=DLQ,
        durable=True,
    )

    channel.queue_declare(
        queue=TARGET_QUEUE,
        durable=True,
    )

    replayed = 0

    while True:
        method, properties, body = channel.basic_get(
            queue=DLQ,
            auto_ack=False,
        )

        if method is None:
            break

        payload = json.loads(
            body.decode("utf-8")
        )

        print()
        print("=" * 70)
        print(f"Replaying: {payload.get('article_key')}")
        print(f"Feed:      {payload.get('feed_id')}")

        # IMPORTANT:
        # Do NOT copy old retry/death headers.
        #
        # We want this to behave like a fresh processing
        # attempt using the newly fixed LLM configuration.
        new_properties = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
            headers={
                "x-retry-count": 0,
            },
        )

        channel.basic_publish(
            exchange="",
            routing_key=TARGET_QUEUE,
            body=body,
            properties=new_properties,
        )

        # Only remove the DLQ copy AFTER the publish succeeds.
        channel.basic_ack(
            delivery_tag=method.delivery_tag
        )

        replayed += 1

        print("Published -> article.processing")
        print("Removed from DLQ.")

    connection.close()

    print()
    print("=" * 70)
    print(f"Replay complete. Messages replayed: {replayed}")
    print("=" * 70)


if __name__ == "__main__":
    main()