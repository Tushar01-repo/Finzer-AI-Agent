import os

import pika
import pytest
from app.config.settings import settings
from app.queue.queue_topology import QueueTopology


RABBITMQ_URL = settings.RABBITMQ_URL


pytestmark = pytest.mark.integration


@pytest.fixture
def rabbitmq_url():
    if not RABBITMQ_URL:
        pytest.skip(
            "RABBITMQ_URL is not configured. "
            "Set it before running RabbitMQ integration tests."
        )

    return RABBITMQ_URL


def test_rabbitmq_connection(rabbitmq_url):
    topology = QueueTopology(
        rabbitmq_url=rabbitmq_url
    )

    connection = topology._create_connection()

    try:
        assert connection.is_open
    finally:
        connection.close()


def test_rabbitmq_topology_declares_all_queues(rabbitmq_url):
    topology = QueueTopology(
        rabbitmq_url=rabbitmq_url
    )

    topology.declare()

    connection = topology._create_connection()

    try:
        channel = connection.channel()

        for queue_name in (
            topology.article_queue,
            topology.retry_queue,
            topology.dlq,
        ):
            result = channel.queue_declare(
                queue=queue_name,
                passive=True,
            )

            assert result.method.queue == queue_name

    finally:
        connection.close()


def test_rabbitmq_queues_are_durable(rabbitmq_url):
    topology = QueueTopology(
        rabbitmq_url=rabbitmq_url
    )

    topology.declare()

    connection = topology._create_connection()

    try:
        channel = connection.channel()

        for queue_name in (
            topology.article_queue,
            topology.retry_queue,
            topology.dlq,
        ):
            result = channel.queue_declare(
                queue=queue_name,
                passive=True,
            )

            assert result.method.queue == queue_name
            assert result.method.durable is True

    finally:
        connection.close()