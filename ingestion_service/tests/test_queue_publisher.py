import json
from unittest.mock import MagicMock, patch

import pytest

from app.queue.queue_publisher import QueuePublisher


def test_publisher_requires_rabbitmq_url():
    publisher = QueuePublisher(
        rabbitmq_url="",
        queue_name="article.processing",
    )

    with pytest.raises(
        ValueError,
        match="RABBITMQ_URL",
    ):
        publisher._create_connection()


@patch("app.queue.queue_publisher.pika.BlockingConnection")
@patch("app.queue.queue_publisher.pika.URLParameters")
def test_create_connection(
    mock_url_parameters,
    mock_blocking_connection,
):
    connection = MagicMock()

    mock_url_parameters.return_value = MagicMock()
    mock_blocking_connection.return_value = connection

    rabbitmq_url = (
        "amqp://user:password@localhost:5672/%2Ffinzer"
    )

    publisher = QueuePublisher(
        rabbitmq_url=rabbitmq_url,
        queue_name="article.processing",
    )

    result = publisher._create_connection()

    mock_url_parameters.assert_called_once_with(
        rabbitmq_url
    )

    mock_blocking_connection.assert_called_once_with(
        mock_url_parameters.return_value
    )

    assert result is connection


@patch("app.queue.queue_publisher.pika.BlockingConnection")
def test_publish_message(mock_blocking_connection):
    connection = MagicMock()
    channel = MagicMock()

    connection.channel.return_value = channel
    mock_blocking_connection.return_value = connection

    publisher = QueuePublisher(
        rabbitmq_url=(
            "amqp://user:password@localhost:5672/%2Ffinzer"
        ),
        queue_name="article.processing",
    )

    message = {
        "article_key": "a" * 64,
        "event": "article.process",
    }

    publisher.publish(message)

    channel.queue_declare.assert_called_once_with(
        queue="article.processing",
        durable=True,
    )

    channel.basic_publish.assert_called_once()

    call_kwargs = channel.basic_publish.call_args.kwargs

    assert call_kwargs["exchange"] == ""
    assert call_kwargs["routing_key"] == "article.processing"

    assert json.loads(
        call_kwargs["body"]
    ) == message

    properties = call_kwargs["properties"]

    assert properties.delivery_mode == 2
    assert properties.content_type == "application/json"

    connection.close.assert_called_once()


@patch("app.queue.queue_publisher.pika.BlockingConnection")
def test_publish_closes_connection_when_publish_fails(
    mock_blocking_connection,
):
    connection = MagicMock()
    channel = MagicMock()

    connection.channel.return_value = channel
    mock_blocking_connection.return_value = connection

    channel.basic_publish.side_effect = RuntimeError(
        "RabbitMQ publish failed"
    )

    publisher = QueuePublisher(
        rabbitmq_url=(
            "amqp://user:password@localhost:5672/%2Ffinzer"
        ),
        queue_name="article.processing",
    )

    with pytest.raises(
        RuntimeError,
        match="RabbitMQ publish failed",
    ):
        publisher.publish(
            {
                "article_key": "a" * 64,
            }
        )

    connection.close.assert_called_once()


def test_custom_queue_name():
    publisher = QueuePublisher(
        rabbitmq_url=(
            "amqp://user:password@localhost:5672/%2Ffinzer"
        ),
        queue_name="custom.queue",
    )

    assert publisher.queue_name == "custom.queue"