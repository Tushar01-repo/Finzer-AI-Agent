import pika

from app.config.settings import settings
from app.queue.queue_topology import QueueTopology


DOCUMENT_QUEUES = [
    "document.embedding",
    "document.embedding.retry.1",
    "document.embedding.retry.2",
    "document.embedding.retry.3",
    "document.embedding.dlq",
]


def main():
    print("=" * 70)
    print("Finzer RabbitMQ Document Queue Setup")
    print("=" * 70)

    # ----------------------------------------------------------
    # 1. Declare complete topology
    # ----------------------------------------------------------

    print("\n[1] Declaring RabbitMQ topology...")

    topology = QueueTopology()
    topology.declare()

    print("    Topology declaration completed.")

    # ----------------------------------------------------------
    # 2. Connect for verification
    # ----------------------------------------------------------

    print("\n[2] Connecting to RabbitMQ...")

    if not settings.RABBITMQ_URL:
        raise ValueError(
            "RABBITMQ_URL is not configured."
        )

    connection = pika.BlockingConnection(
        pika.URLParameters(
            settings.RABBITMQ_URL
        )
    )

    try:
        channel = connection.channel()

        print("    Connected.")

        # ------------------------------------------------------
        # 3. Passive queue verification
        #
        # passive=True means:
        # "check that this queue exists; don't create it"
        # ------------------------------------------------------

        print("\n[3] Verifying document queues...")

        for queue_name in DOCUMENT_QUEUES:
            result = channel.queue_declare(
                queue=queue_name,
                passive=True,
            )

            message_count = (
                result.method.message_count
            )

            consumer_count = (
                result.method.consumer_count
            )

            print(
                f"    [OK] {queue_name:<32} "
                f"messages={message_count:<4} "
                f"consumers={consumer_count}"
            )

    finally:
        connection.close()

    print("\n" + "=" * 70)
    print("DOCUMENT RABBITMQ TOPOLOGY PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()