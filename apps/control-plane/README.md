# AIP Control Plane
Enterprise Control Plane microservice based on Domain-Driven Design (DDD) inspired by DCP Platform.

## Endpoint catalog

On startup, the control plane idempotently provisions the built-in API endpoint
catalog in MongoDB. Catalog metadata is refreshed from the application, while
admin-managed endpoint export statuses are preserved. MongoDB must be reachable
for the catalog to be available; initialization failures are logged and the
service starts in its existing degraded mode.
