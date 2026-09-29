# Stateful HA migration

The infrastructure chart now applies mandatory pod anti-affinity and
PodDisruptionBudgets to the current StatefulSets. This protects availability
during voluntary node drains, but it does not by itself create database
failover.

The production migration target is operator-managed infrastructure:

- MongoDB Community Operator with a replica set and tested backup/restore.
- RabbitMQ Cluster Operator with quorum queues.
- Redis Operator with Sentinel or Redis Cluster, matching the client topology.
- MinIO Operator with a distributed Tenant and erasure-coded storage.

The existing StatefulSets must remain enabled until the replacement has been
validated in a separate namespace or cluster. Do not install an Operator
resource over the existing resources with the same service or PVC names.

Migration gates:

1. Install and pin each Operator and its CRDs.
2. Create the operator-managed instance in a migration namespace.
3. Restore a backup and validate application connectivity and failover.
4. Run a workload and node-drain test.
5. Cut clients over to the new service names.
6. Keep the old data available through the rollback window.
7. Only then remove the legacy StatefulSets and their PVCs.

The `highAvailability` values in `aip-infra` are deliberately enabled by
default because they are safe for the current deployment. Operator CRs are not
auto-applied until the target operator versions, storage classes, backup
locations, and service cutover names are selected for the cluster.
