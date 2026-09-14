# Lifecycle settings

Lifecycle labels in generated docs are an alpha feature. Please [share feedback](https://github.com/canton-network/cf-docs/issues).

## OpenAPI

```yaml
paths:
  /example:
    get:
      operationId: getExample
      x-state: pre-alpha
      responses:
        '200':
          description: OK
```

Accepted values: `pre-alpha`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

An operation tag `pre-alpha` is also recognized when `x-state` is absent; native deprecation takes precedence over the tag.

## AsyncAPI

```yaml
channels:
  payments.created:
    x-state: pre-alpha
    subscribe:
      x-state: beta
      message:
        payload:
          type: string
  payments.legacy:
    x-state: deprecated
```

Accepted `x-state` values: `pre-alpha`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## OpenRPC

```json
{
  "methods": [{
    "name": "getExample",
    "x-state": "pre-alpha",
    "params": [],
    "result": {"name": "result", "schema": {"type": "string"}}
  }]
}
```

Accepted `x-state` values: `pre-alpha`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## TypeDoc

```ts
/** @preAlpha */
export interface Example {
  id: string;
}

/** @deprecated Use Example instead. */
export interface LegacyExample {
  id: string;
}
```

Accepted lifecycle tags: `@preAlpha`, `@alpha`, `@beta`, `@stable`, `@deprecated`.

## Protobuf/gRPC

```yaml
# Descriptor manifest
metadata_path: lifecycle.json
```

```json
{
  "endpoints": {
    "example.PaymentService/CreatePayment": {"lifecycle": {"state": "beta"}}
  },
  "messages": {
    "example.CreatePaymentRequest": {"lifecycle": {"state": "deprecated"}}
  }
}
```

Accepted `lifecycle.state` values: `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## Daml

```daml
module Example {-# WARNING "Alpha: experimental module." #-} where

{-# WARNING Token "Beta: preview type." #-}
data Token = Token
```

```daml
module LegacyExample {-# DEPRECATED "Use Example instead." #-} where
```

Accepted `WARNING` prefixes: `Alpha:`, `Beta:`, `Stable:` (case-insensitive). Explicit prefixes override legacy matching of `alpha` or `beta` anywhere in warning text; otherwise `alpha` wins over `beta`. Deprecation uses `DEPRECATED` and takes precedence.
