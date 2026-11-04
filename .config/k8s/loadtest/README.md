# k6 压测

```bash
kubectl apply -k .config/k8s/loadtest

K6_JOB="blog-k6-$(date +%Y%m%d%H%M%S)"
kubectl -n blog create job "$K6_JOB" --from=cronjob/blog-k6
kubectl -n blog logs -f "job/$K6_JOB" --pod-running-timeout=120s
kubectl -n blog get job "$K6_JOB"
```
