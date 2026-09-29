# External Secrets setup

The Kubernetes and Helm deployments use External Secrets Operator (ESO). Plaintext
credentials are not stored in this repository.

Before deploying the platform:

1. Install ESO in the cluster.
2. Create a `ClusterSecretStore` named `aip-platform`.
3. Provision the following remote records in the configured secret backend:

| Remote key | Properties |
| --- | --- |
| `aip-platform/mongodb` | `username`, `password` |
| `aip-platform/redis` | `password` |
| `aip-platform/rabbitmq` | `username`, `password` |
| `aip-platform/minio` | `username`, `password` |
| `aip-platform/control-plane` | `mongo-uri`, `redis-uri`, `rabbitmq-uri`, `jwt-secret`, `master-pepper` |
| `aip-platform/runtimes` | `mongo-uri`, `redis-uri`, `rabbitmq-uri` |

The Helm charts use the same defaults as the bootstrap manifests. Override
`externalSecrets.secretStoreRef` and the remote key values per environment.
The `ClusterSecretStore` credentials and provider configuration must be managed
outside this repository.
