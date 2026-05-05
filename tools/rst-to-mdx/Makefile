BINARY := rst-to-mdx
DIST   := dist
GO     ?= go
OS_ARCHES := darwin/arm64 darwin/amd64 linux/arm64 linux/amd64 windows/amd64

.PHONY: all build test fmt vet tidy smoke release clean

all: build

build:
	$(GO) build -o $(BINARY) ./cmd/rst-to-mdx

test:
	$(GO) test ./...

fmt:
	$(GO) fmt ./...

vet:
	$(GO) vet ./...

tidy:
	$(GO) mod tidy

smoke: build
	./smoke-test.sh

# Cross-compile to dist/<os>-<arch>/ for publishing via
# `dpm artifacts publish component`.
#
# Each platform directory gets a component.yaml whose `path:` matches the
# platform's binary name. Windows uses component.windows.yaml (`.exe`
# suffix); every other platform uses the default component.yaml.
release:
	@rm -rf $(DIST)
	@for pair in $(OS_ARCHES); do \
	  os=$${pair%/*}; arch=$${pair#*/}; \
	  out=$(DIST)/$$os-$$arch; \
	  mkdir -p $$out; \
	  ext=""; if [ "$$os" = "windows" ]; then ext=".exe"; fi; \
	  echo ">> $$os/$$arch"; \
	  GOOS=$$os GOARCH=$$arch $(GO) build -o $$out/$(BINARY)$$ext ./cmd/rst-to-mdx; \
	  if [ "$$os" = "windows" ]; then \
	    cp component.windows.yaml $$out/component.yaml; \
	  else \
	    cp component.yaml $$out/; \
	  fi; \
	  cp LICENSE $$out/; \
	done

clean:
	rm -f $(BINARY)
	rm -rf $(DIST)
