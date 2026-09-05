
## ✅ Lỗi này nghĩa là gì

`kubectl` chưa được cài trên WSL/Ubuntu của bạn.  
Vì vậy lệnh:

```bash
kubectl get ns
```

không chạy được.

---

## 🔧 Cài đặt `kubectl` trên Ubuntu/WSL

Dùng cách chính thức từ Kubernetes:

```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client
```

Nếu muốn kiểm tra lại:

```bash
kubectl version --client
```

---

## 🔧 Nếu cần cả `helm`

Repo của bạn dùng Helm để deploy, nên cài thêm:

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

---

## ✅ Sau khi cài xong, chạy lại

Trong venv của repo:

```bash
source .venv/bin/activate
kubectl get ns
```

Nếu chưa có cluster config, bạn sẽ thấy lỗi kiểu:

- `The connection to the server localhost:8080 was refused`
- `No context exists`

Khi đó cần:

```bash
kubectl config get-contexts
kubectl config current-context
```

Nếu cluster chưa được kết nối, bạn cần import kubeconfig của cluster:

```bash
export KUBECONFIG=/path/to/your/kubeconfig
kubectl get ns
```

---

## 📌 Cho repo của bạn

Bạn đang deploy theo Helm và Kubernetes, nên cần tối thiểu:

- `kubectl`
- `helm`
- `kubeconfig` hợp lệ
- quyền truy cập vào cluster

Khi đã xong, bạn có thể dùng các lệnh trong `runbook.md` để deploy:

```bash
kubectl apply -f deploy/k8s/namespaces/namespaces.yaml
helm upgrade --install aip-infra deploy/helm/aip-infra --namespace aip-infra --create-namespace --wait
helm upgrade --install aip-control deploy/helm/aip-control --namespace aip-control --create-namespace --wait
helm upgrade --install aip-runtimes deploy/helm/aip-runtimes --namespace aip-multimodal --create-namespace --wait
```

---

## 🚀 Bước tiếp theo

Bạn muốn tôi làm tiếp không?

1. Cài đặt `kubectl` và `helm` cho bạn bằng lệnh từng bước  
2. Hướng dẫn tạo kubeconfig từ cluster  
3. Chạy luôn check `kubectl get ns` sau khi cài xong