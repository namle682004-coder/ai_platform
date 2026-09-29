"""
AIP Dispatcher Task Consumer package.
Consumes tasks from RabbitMQ and orchestrates resolution, execution, retries, and events.
"""

from .task_consumer import TaskConsumer

__all__ = ["TaskConsumer"]
