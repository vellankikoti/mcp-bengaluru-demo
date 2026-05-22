.PHONY: up down reset smoke agent inject-oom inject-retry inject-cascade inject-dns recover setup-tmux checkpoint preflight test

CLUSTER_NAME := mcp-demo
KUBECONFIG_PATH := $(HOME)/.kube/mcp-demo.yaml
CONTEXT := kind-$(CLUSTER_NAME)

up:
	@bash demo/bootstrap.sh

down:
	kind delete cluster --name $(CLUSTER_NAME)

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
	@python3 -m pytest tests/test_policy.py tests/test_recordings.py tests/test_tools_schema.py -v --tb=short --asyncio-mode=auto
