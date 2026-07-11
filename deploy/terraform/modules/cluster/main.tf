# Managed Kubernetes cluster hosting deploy/k8s. Private control plane,
# no public node IPs, workload identity wired to module.kms for secret
# access — services should never hold long-lived cloud credentials as
# pod env vars.
