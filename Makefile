SHELL := /bin/bash
REGISTRY ?= docker.io
IMG ?= jburks725/route53dynip
VERSION ?= 1

# Architectures we can build for
ARCHES = linux/amd64,linux/arm64

.PHONY: update-base
update-base:
	base=$$(grep FROM Dockerfile | awk '{print $$2}') ;\
	docker pull $$base

.PHONY: docker-build-local
docker-build-local:
	docker build --no-cache -f Dockerfile -t $(IMG):$(VERSION) . ;\
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

# New targets for testing
.PHONY: test
test:
	python run_tests.py

.PHONY: test-coverage
test-coverage:
	python -m coverage run --source=. run_tests.py
	python -m coverage report -m
	python -m coverage html

.PHONY: test-docker
test-docker:
	docker build -f Dockerfile.test -t $(IMG):test .
	docker run --rm $(IMG):test
