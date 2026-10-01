"""Re-export topology constants from common.messaging.topology."""

from common.messaging.topology import (
    CORE_TASK_DOMAINS,
    EXCHANGE_DLX,
    EXCHANGE_EVENTS,
    EXCHANGE_JOBS,
    EXCHANGE_JOBS_DLX,
    EXCHANGE_JOBS_RETRY,
    EXCHANGE_RETRIES,
    EXCHANGE_TASKS,
    QUEUE_CALLBACKS,
    QUEUE_DLQ,
    SRS_JOB_TYPES,
    setup_rabbitmq_topology,
)

__all__ = [
    "CORE_TASK_DOMAINS",
    "EXCHANGE_DLX",
    "EXCHANGE_EVENTS",
    "EXCHANGE_JOBS",
    "EXCHANGE_JOBS_DLX",
    "EXCHANGE_JOBS_RETRY",
    "EXCHANGE_RETRIES",
    "EXCHANGE_TASKS",
    "QUEUE_CALLBACKS",
    "QUEUE_DLQ",
    "SRS_JOB_TYPES",
    "setup_rabbitmq_topology",
]
