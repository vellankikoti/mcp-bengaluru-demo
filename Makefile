.PHONY: up down reset smoke agent inject-oom inject-retry inject-cascade inject-dns recover setup-tmux checkpoint preflight test

# Cluster-agnostic: uses current kubectl context by default.
# Override: make up KUBE_CONTEXT=my-context
# To create a new kind cluster: ensure kind is installed, then make up
KUBE_CONTEXT ?= $(shell kubectl config current-context 2>/dev/null || echo "")

export KUBE_CONTEXT

up:
	@bash demo/bootstrap.sh

down:
	@if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q mcp-demo; then \
	  echo "Deleting kind cluster mcp-demo..."; \
	  kind delete cluster --name mcp-demo; \
	else \
	  echo "Removing demo namespaces from cluster (context: $(KUBE_CONTEXT))..."; \
	  kubectl --context=$(KUBE_CONTEXT) delete namespace production mcp-system --ignore-not-found 2>/dev/null || true; \
	  kubectl --context=$(KUBE_CONTEXT) delete namespace observability --ignore-not-found 2>/dev/null || true; \
	  kubectl --context=$(KUBE_CONTEXT) delete clusterrolebinding mcp-incident-agent --ignore-not-found 2>/dev/null || true; \
	  echo "Demo resources removed. Cluster itself is unchanged."; \
	fi

reset:
	@bash demo/reset.sh

smoke:
	@bash demo/smoke-test.sh

agent:
	@bash agent/start.sh

inject-oom:
	@bash demo/inject-incident.sh crashloop-oom

inject-retry:
	@bash demo/inject-incident.sh retry-storm

inject-cascade:
	@bash demo/inject-incident.sh cascade

inject-dns:
	@bash demo/inject-incident.sh dns-failure

inject-cert:
	@bash demo/inject-incident.sh cert-expiry

inject-hpa:
	@bash demo/inject-incident.sh stuck-hpa

inject-bad-rollout:
	@bash demo/inject-incident.sh bad-rollout

recover:
	@bash demo/inject-incident.sh recover

setup-tmux:
	@bash demo/setup-tmux.sh

checkpoint:
	@bash demo/recovery/save-checkpoint.sh

emergency-reset:
	@bash demo/recovery/emergency-reset.sh

preflight:
	@bash demo/preflight.sh

test:
	@python3 -m pytest tests/ -v --tb=short --asyncio-mode=auto
