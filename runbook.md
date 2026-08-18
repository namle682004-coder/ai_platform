

## Runbook deploy và quản lý Kubernetes cho AIP

Dựa trên cấu trúc hiện có trong repo: `aip-infra`, `aip-control`, `aip-runtimes`, `namespaces.yaml`, và `cd.yml`.

---

## 1. Mục tiêu

Runbook này hướng dẫn:

- chuẩn bị cluster Kubernetes
- deploy infra nền tảng
- deploy gateway/control plane
- deploy AI runtimes
- kiểm tra sức khỏe hệ thống
- rollback, scale, restart, log, và troubleshoot

---

## 2. Điều kiện tiên quyết

### 2.1 Công cụ cần có
- kubectl
- helm
- gh hoặc GitHub access nếu dùng CI/CD
- quyền truy cập vào cluster
- kubeconfig hợp lệ

### 2.2 Namespace cần có
Theo `namespaces.yaml`:

```bash
kubectl apply -f deploy/k8s/namespaces/namespaces.yaml
```

Kiểm tra:

```bash
kubectl get ns
```

---

## 3. Cấu trúc cluster theo repo

- `aip-infra`: MongoDB, Redis, RabbitMQ, MinIO
- `aip-control`: Gateway / control plane
- `aip-multimodal`: GPU AI workloads
- `aip-text`: CPU text services
- `aip-observability`: monitoring

Bạn có thể xem thêm trong `values.yaml` và `values.yaml`.

---

## 4. Chuẩn bị secret và config

Trước khi deploy, cần đảm bảo:

- secret cho MongoDB
- secret cho Redis
- secret cho RabbitMQ
- secret cho MinIO
- kubeconfig cluster
- image tags chính xác

Check các secret templates trong `secrets.yaml` và `values.yaml`.

Ví dụ:

```bash
kubectl get secrets -A
kubectl describe secret -n aip-infra
```

> Nếu thiếu secret, deploy sẽ fail ở bước tạo service hoặc pod.

---

## 5. Deploy infra

### 5.1 Deploy infra chart
```bash
helm upgrade --install aip-infra deploy/helm/aip-infra \
  --namespace aip-infra \
  --create-namespace \
  --wait \
  --timeout 5m
```

### 5.2 Kiểm tra pods
```bash
kubectl get pods -n aip-infra
kubectl get svc -n aip-infra
kubectl get pvc -n aip-infra
```

### 5.3 Kiểm tra health
```bash
kubectl logs -n aip-infra deployment/<mongodb-pod-name>
kubectl logs -n aip-infra deployment/<redis-pod-name>
kubectl logs -n aip-infra deployment/<rabbitmq-pod-name>
```

---

## 6. Deploy gateway / control plane

### 6.1 Deploy chart
```bash
helm upgrade --install aip-control deploy/helm/aip-control \
  --namespace aip-control \
  --create-namespace \
  --set image.tag=YOUR_TAG \
  --wait \
  --timeout 5m
```

### 6.2 Kiểm tra
```bash
kubectl get pods -n aip-control
kubectl get svc -n aip-control
kubectl get ingress -n aip-control
kubectl describe deploy -n aip-control
```

### 6.3 Kiểm tra logs
```bash
kubectl logs -n aip-control deployment/aip-gateway
```

---

## 7. Deploy AI runtimes

### 7.1 Deploy chart
```bash
helm upgrade --install aip-runtimes deploy/helm/aip-runtimes \
  --namespace aip-multimodal \
  --create-namespace \
  --set stt.image.tag=YOUR_TAG \
  --set tts.image.tag=YOUR_TAG \
  --set translation.image.tag=YOUR_TAG \
  --set moderation.image.tag=YOUR_TAG \
  --set ocr.image.tag=YOUR_TAG \
  --wait \
  --timeout 10m
```

### 7.2 Kiểm tra workloads
```bash
kubectl get pods -A | grep -E 'stt|tts|translation|moderation|ocr'
kubectl get hpa -A
```

### 7.3 Kiểm tra resource
```bash
kubectl top pods -A
kubectl top nodes
```

---

## 8. Kiểm tra sức khỏe sau deploy

### 8.1 Pod readiness
```bash
kubectl get pods -A -o wide
kubectl get pods -A --field-selector=status.phase!=Running
```

### 8.2 Service connectivity
```bash
kubectl get svc -A
kubectl get endpoints -A
```

### 8.3 Ingress
```bash
kubectl get ingress -A
kubectl describe ingress -n aip-control
```

### 8.4 Rollout status
```bash
kubectl rollout status deployment/aip-gateway -n aip-control --timeout=180s
```

---

## 9. Quản lý kubernetes hằng ngày

### 9.1 Scale
Scale deployment thủ công:

```bash
kubectl scale deployment/aip-gateway -n aip-control --replicas=3
kubectl scale deployment/<service> -n aip-multimodal --replicas=2
```

### 9.2 Restart
```bash
kubectl rollout restart deployment/aip-gateway -n aip-control
kubectl rollout status deployment/aip-gateway -n aip-control
```

### 9.3 Rollback
```bash
helm history aip-control -n aip-control
helm rollback aip-control 1 -n aip-control
```

Hoặc với deployment:

```bash
kubectl rollout undo deployment/aip-gateway -n aip-control
```

### 9.4 Xem logs
```bash
kubectl logs -n aip-control deployment/aip-gateway --tail=100
kubectl logs -n aip-multimodal deployment/<pod-name> --previous
```

### 9.5 Xem events
```bash
kubectl get events -A --sort-by=.metadata.creationTimestamp
```

---

## 10. Rollback và khôi phục

### 10.1 Rollback Helm
```bash
helm list -A
helm rollback aip-control 1 -n aip-control
helm rollback aip-runtimes 1 -n aip-multimodal
```

### 10.2 Rollback infra
```bash
helm rollback aip-infra 1 -n aip-infra
```

### 10.3 Restore dữ liệu
Nếu dùng backup Mongo/MinIO, cần chạy script trong `backup_mongodb.sh`. Kiểm tra lại nội dung và test restore trong môi trường non-prod trước.

---

## 11. Troubleshooting thường gặp

### 11.1 Pod Pending
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace>
```

Nguyên nhân thường gặp:
- thiếu resource node
- taint/toleration không phù hợp
- PVC chưa bind
- image pull errors

### 11.2 CrashLoopBackOff
```bash
kubectl logs <pod-name> -n <namespace> --previous
kubectl describe pod <pod-name> -n <namespace>
```

Kiểm tra:
- env missing
- secret missing
- DB connection fail
- port mismatch

### 11.3 ImagePullBackOff
```bash
kubectl describe pod <pod-name> -n <namespace>
docker pull ghcr.io/<repo>/<image>:<tag>
```

### 11.4 Ingress không route
```bash
kubectl get ingress -A
kubectl describe ingress -n aip-control
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller
```

---

## 12. Giám sát và cảnh báo

Repo đã có cấu hình monitoring ở:

- `prometheus.yml`
- `sla-alerts.yml`

Kiểm tra:

```bash
kubectl get pods -n aip-observability
kubectl port-forward -n aip-observability svc/prometheus 9090:9090
```

Mở browser:
- http://localhost:9090

---

## 13. Checklist deploy trước khi release

- [ ] kubeconfig valid
- [ ] namespace đã apply
- [ ] secrets đã tồn tại
- [ ] image tag đúng
- [ ] helm dependency đã load
- [ ] pod đang Running
- [ ] service lên đúng port
- [ ] ingress có endpoint
- [ ] HPA hoạt động
- [ ] logs không lỗi
- [ ] backup test chạy
- [ ] rollback plan sẵn sàng

---

## 14. Quy trình deploy chuẩn cho repo này

### Deploy mới:
```bash
kubectl apply -f deploy/k8s/namespaces/namespaces.yaml

helm upgrade --install aip-infra deploy/helm/aip-infra --namespace aip-infra --create-namespace --wait
helm upgrade --install aip-control deploy/helm/aip-control --namespace aip-control --create-namespace --set image.tag=YOUR_TAG --wait
helm upgrade --install aip-runtimes deploy/helm/aip-runtimes --namespace aip-multimodal --create-namespace --set stt.image.tag=YOUR_TAG --set tts.image.tag=YOUR_TAG --set translation.image.tag=YOUR_TAG --set moderation.image.tag=YOUR_TAG --set ocr.image.tag=YOUR_TAG --wait
```

### Validate:
```bash
kubectl get pods -A
kubectl get svc -A
kubectl logs -n aip-control deployment/aip-gateway
kubectl rollout status deployment/aip-gateway -n aip-control
```

---

## 15. Kết luận

Runbook này là chuẩn cho môi trường Kubernetes của repo bạn: deploy từng tầng rõ ràng, quản lý theo namespace, dùng Helm làm orchestration chính, và dùng kubectl để vận hành hằng ngày.

