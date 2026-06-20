.DEFAULT_GOAL := help

COMPOSE_FILE ?= bfd9000_web/docker-compose.yml
MOCK_BFD9010_IMAGE ?= mock-bfd9010:local

.PHONY: help build-test-docker run-test-docker build-mock-bfd9010 mock-bfd9010

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build-test-docker: ## Build test Docker image with compose
	load-podman
	podman-compose -f $(COMPOSE_FILE) build

set-media-volume-permissions: ## Set permissions for media volume to allow non-root access: see dockers.md
	podman run --rm -v bfd9000_media_volume:/data alpine sh -c "chown -R 1000:1000 /data"

run-test-docker: set-media-volume-permissions ## Run test Docker stack with compose
	podman-compose -f $(COMPOSE_FILE) up

build-mock-bfd9010: ## Build mock BFD9010 Docker image
	podman build -t $(MOCK_BFD9010_IMAGE) dev_tools/mock_bfd9010

mock-bfd9010: ## Start the mock BFD9010 scanner service on port 5000
	python dev_tools/mock_bfd9010/mock_bfd9010.py --host localhost
