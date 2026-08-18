# Everwin AI Platform - Service Level Agreement (SLA)

## 1. Scope

This SLA applies to all Everwin AI Platform API endpoints served through the AIP Gateway,
including but not limited to: Chat Completions, Speech-to-Text, Text-to-Speech, OCR,
Translation, Moderation, Embeddings, and Image Generation APIs.

## 2. Uptime Commitment

| Tier        | Monthly Uptime | Max Downtime/Month | Support Response |
|-------------|---------------|-------------------|-----------------|
| Standard    | 99.5%         | ~3h 39m           | 24h             |
| Professional| 99.9%         | ~43m              | 4h              |
| Enterprise  | 99.95%        | ~21m              | 1h              |

**Uptime** = (Total Minutes - Downtime Minutes) / Total Minutes × 100

**Excluded from downtime**: Scheduled maintenance (announced 48h in advance), force majeure.

## 3. Latency Targets

| Metric        | Standard     | Professional | Enterprise  |
|--------------|-------------|-------------|------------|
| P50 Latency  | ≤ 100ms     | ≤ 80ms     | ≤ 50ms    |
| P95 Latency  | ≤ 300ms     | ≤ 200ms    | ≤ 150ms   |
| P99 Latency  | ≤ 1000ms    | ≤ 500ms    | ≤ 300ms   |

*Measured at the gateway level, excluding model inference time for generative AI endpoints.*

## 4. Error Rate

| Tier        | Max 5xx Error Rate |
|-------------|-------------------|
| Standard    | ≤ 1.0%            |
| Professional| ≤ 0.5%            |
| Enterprise  | ≤ 0.1%            |

## 5. Throughput Guarantees

| Tier        | Guaranteed RPS | Burst RPS |
|-------------|---------------|-----------|
| Standard    | 50 rps        | 100 rps   |
| Professional| 200 rps       | 500 rps   |
| Enterprise  | 1000 rps      | 2000 rps  |

## 6. Data Durability & Security

- MongoDB: 3-replica ReplicaSet with daily backups, 30-day retention
- MinIO: Erasure coding (4-node), 99.999% object durability
- All data encrypted at rest (AES-256) and in transit (TLS 1.3)
- API keys hashed with SHA-256, never stored in plaintext

## 7. SLA Credit Schedule

| Uptime Achieved       | Credit (% of monthly fee) |
|-----------------------|--------------------------|
| 99.0% – 99.5%        | 10%                      |
| 95.0% – 99.0%        | 25%                      |
| 90.0% – 95.0%        | 50%                      |
| Below 90.0%          | 100%                     |

## 8. Monitoring & Reporting

- Real-time status page: `/status`
- Prometheus + Grafana dashboards available for Enterprise customers
- Monthly SLA compliance reports delivered via email
- Incident post-mortems published within 5 business days

## 9. Maintenance Windows

- Scheduled maintenance: Sunday 02:00-06:00 UTC (announced 48h in advance)
- Emergency maintenance: As needed with immediate notification
- Zero-downtime deployments via rolling updates (standard procedure)

## 10. Escalation Path

| Level | Contact           | Response Time |
|-------|-------------------|---------------|
| L1    | support@everwin.ai | 4h           |
| L2    | engineering@everwin.ai | 2h        |
| L3    | cto@everwin.ai     | 1h           |
