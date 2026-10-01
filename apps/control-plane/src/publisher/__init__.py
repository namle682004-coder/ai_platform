"""Control-Plane Publisher (Re-exports from common.messaging for backward compatibility)."""

from common.messaging import (
    setup_rabbitmq_topology,
    EXCHANGE_JOBS,
    EXCHANGE_JOBS_RETRY,
    EXCHANGE_JOBS_DLX,
    EXCHANGE_TASKS,
    EXCHANGE_EVENTS,
    EXCHANGE_DLX,
    QUEUE_CALLBACKS,
    CORE_TASK_DOMAINS,
    SRS_JOB_TYPES,
    TaskPublisher,
)

__all__ = [
    "setup_rabbitmq_topology",
    "EXCHANGE_JOBS",
    "EXCHANGE_JOBS_RETRY",
    "EXCHANGE_JOBS_DLX",
    "EXCHANGE_TASKS",
    "EXCHANGE_EVENTS",
    "EXCHANGE_DLX",
    "QUEUE_CALLBACKS",
    "CORE_TASK_DOMAINS",
    "SRS_JOB_TYPES",
    "TaskPublisher",
]
