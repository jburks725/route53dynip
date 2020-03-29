SHELL := /bin/bash
REGISTRY ?= docker.io
IMG ?= jburks725/route53dynip
VERSION ?= 1

# Architectures we can build for
ARCHES = linux/amd64,linux/arm/v7,linux/arm64

.PHONY: update-base
update-base:
	base=$$(grep FROM Dockerfile | awk '{print $$2}') ;\
	docker pull $$base

.PHONY: docker-build-local
docker-build-local:
	docker build -f Dockerfile -t $(IMG):$(VERSION) . ;\
	docker tag $(IMG):$(VERSION) $(IMG):latest ;\

.PHONY: docker-push
docker-push: docker-build-local
	docker manifest push $(IMG):$(VERSION) ;\
	docker manifest push $(IMG):latest

.PHONY: docker-multiarch
docker-multiarch:
	docker buildx create --use ;\
	docker buildx build --platform $(ARCHES) -t $(IMG):$(VERSION) -t $(IMG):latest --push . ;\
	docker buildx rm

.PHONY: clean
clean:
	docker rmi $(IMG):$(VERSION) || true ;\
	docker rmi $(IMG):latest || true
