# Deployment (Phase 14 — Cloud Native)

Container image + Kubernetes/Helm packaging for the WIDS pipeline services.

## Build the image

```bash
docker build -f deploy/Dockerfile -t wids:0.14.0 .
# inference image with the ML stack (torch/tf):
docker build -f deploy/Dockerfile --build-arg WITH_ML=1 -t wids:0.14.0-ml .
```

One image runs any service, selected by `WIDS_SERVICE`
(`feature-extractor` | `inference` | `response` | `sink`).

## Deploy

**Helm (parameterized):**
```bash
helm install wids deploy/helm/wids \
  --namespace wids --create-namespace \
  --set secret.WIDS_ES_PASSWORD=... --set secret.WIDS_MSSQL_PASSWORD=...
```

**Plain manifests (rendered defaults):**
```bash
kubectl apply -f deploy/k8s/wids-rendered.yaml
```

Each pipeline service is a Deployment with a HorizontalPodAutoscaler (CPU-based;
requires metrics-server), matching the SAD §10 namespace/scaling model. Point
`WIDS_*` config at your in-cluster or external Kafka / Redis / Elasticsearch /
MSSQL. HPAs realize the "horizontal scaling" step of the roadmap.

## Notes

- LocalDB is host-only; in a cluster use a networked SQL Server (set
  `WIDS_MSSQL_SERVER` + credentials in the Secret).
- The GPU inference tier should schedule onto a GPU node pool (add nodeSelector/
  tolerations + `nvidia.com/gpu` resource requests for real GPU nodes).
- Image build/push and cluster apply are CI/cluster steps; manifests here are
  validated for schema/syntax offline.
