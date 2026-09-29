"""
AIP Dispatcher Task Resolver.
Resolves task domains and model aliases into target gRPC connection endpoints.
"""

from .task_resolver import TaskResolver, RuntimeTarget, task_resolver

__all__ = ["TaskResolver", "RuntimeTarget", "task_resolver"]
