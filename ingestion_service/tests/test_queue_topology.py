from unittest.mock import MagicMock

import pytest

from app.queue.queue_topology import QueueTopology


def test_requires_rabbitmq_url():
    topology = QueueTopology(rabbitmq_url="")

    with pytest.raises(ValueError, match="RABBITMQ_URL is not configured"):
        topology._create_connection()


def test_create_connection(monkeypatch):
    mock_connection = MagicMock()
    mock_blocking_connection = MagicMock(
        return_value=mock_connection
    )

    monkeypatch.setattr(
        "app.queue.queue_topology.pika.BlockingConnection",
        mock_blocking_connection,
    )

    topology = QueueTopology(
        rabbitmq_url="amqp://user:password@localhost:5672/%2Ffinzer"
    )

    connection = topology._create_connection()

    assert connection is mock_connection
    mock_blocking_connection.assert_called_once()


def test_declare_all_queues(monkeypatch):
    mock_channel = MagicMock()
    mock_connection = MagicMock()

    mock_connection.channel.return_value = mock_channel

    monkeypatch.setattr(
        "app.queue.queue_topology.pika.BlockingConnection",
        MagicMock(return_value=mock_connection),
    )

    topology = QueueTopology(
        rabbitmq_url="amqp://user:password@localhost:5672/%2Ffinzer"
    )

    topology.declare()

    assert mock_channel.queue_declare.call_count == 3

    declared_queues = [
        call.kwargs["queue"]
        for call in mock_channel.queue_declare.call_args_list
    ]

    assert topology.article_queue in declared_queues
    assert topology.retry_queue in declared_queues
    assert topology.dlq in declared_queues


def test_all_queues_are_durable(monkeypatch):
    mock_channel = MagicMock()
    mock_connection = MagicMock()

    mock_connection.channel.return_value = mock_channel

    monkeypatch.setattr(
        "app.queue.queue_topology.pika.BlockingConnection",
        MagicMock(return_value=mock_connection),
    )

    topology = QueueTopology(
        rabbitmq_url="amqp://user:password@localhost:5672/%2Ffinzer"
    )

    topology.declare()

    for call in mock_channel.queue_declare.call_args_list:
        assert call.kwargs["durable"] is True


def test_connection_is_closed_after_successful_declaration(monkeypatch):
    mock_channel = MagicMock()
    mock_connection = MagicMock()

    mock_connection.channel.return_value = mock_channel

    monkeypatch.setattr(
        "app.queue.queue_topology.pika.BlockingConnection",
        MagicMock(return_value=mock_connection),
    )

    topology = QueueTopology(
        rabbitmq_url="amqp://user:password@localhost:5672/%2Ffinzer"
    )

    topology.declare()

    mock_connection.close.assert_called_once()


def test_connection_is_closed_when_declaration_fails(monkeypatch):
    mock_channel = MagicMock()
    mock_connection = MagicMock()

    mock_connection.channel.return_value = mock_channel

    mock_channel.queue_declare.side_effect = RuntimeError(
        "RabbitMQ declaration failed"
    )

    monkeypatch.setattr(
        "app.queue.queue_topology.pika.BlockingConnection",
        MagicMock(return_value=mock_connection),
    )

    topology = QueueTopology(
        rabbitmq_url="amqp://user:password@localhost:5672/%2Ffinzer"
    )

    with pytest.raises(
        RuntimeError,
        match="RabbitMQ declaration failed",
    ):
        topology.declare()

    mock_connection.close.assert_called_once()


def test_custom_queue_names(monkeypatch):
    mock_channel = MagicMock()
    mock_connection = MagicMock()

    mock_connection.channel.return_value = mock_channel

    monkeypatch.setattr(
        "app.queue.queue_topology.pika.BlockingConnection",
        MagicMock(return_value=mock_connection),
    )

    topology = QueueTopology(
        rabbitmq_url="amqp://user:password@localhost:5672/%2Ffinzer",
        article_queue="custom.processing",
        retry_queue="custom.retry",
        dlq="custom.dlq",
    )

    topology.declare()

    declared_queues = [
        call.kwargs["queue"]
        for call in mock_channel.queue_declare.call_args_list
    ]

    assert declared_queues == [
        "custom.processing",
        "custom.retry",
        "custom.dlq",
    ]