# Lifecycle settings

Lifecycle labels in generated docs are an alpha feature. Please [share feedback](https://github.com/canton-network/cf-docs/issues).

`dev` hides an API until its latest observed version at or before the publish version has another label (or no label). Removal alone does not make a dev API public. Applies to OpenAPI operations, AsyncAPI channel actions, OpenRPC methods, TypeDoc exports, and Daml modules/functions.

## OpenAPI

```yaml
paths:
  /example:
    get:
      operationId: getExample
      x-state: dev
      responses:
        '200':
          description: OK
```

Accepted values: `dev`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## AsyncAPI

```yaml
channels:
  payments.created:
    x-state: dev
    subscribe:
      x-state: beta
      message:
        payload:
          type: string
  payments.legacy:
    x-state: deprecated
```

Accepted `x-state` values: `dev`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## OpenRPC

```json
{
  "methods": [{
    "name": "getExample",
    "x-state": "dev",
    "params": [],
    "result": {"name": "result", "schema": {"type": "string"}}
  }]
}
```

Accepted `x-state` values: `dev`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## TypeDoc

```ts
/** @dev */
export interface Example {
  id: string;
}

/** @deprecated Use Example instead. */
export interface LegacyExample {
  id: string;
}
```

Accepted lifecycle tags: `@dev`, `@alpha`, `@beta`, `@stable`, `@deprecated`.

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
module Example {-# WARNING "Dev: unreleased module." #-} where

{-# WARNING Token "Beta: preview type." #-}
data Token = Token
```

```daml
module LegacyExample {-# DEPRECATED "Use Example instead." #-} where
```

Accepted `WARNING` prefixes: `Dev:`, `Alpha:`, `Beta:`, `Stable:` (case-insensitive). Explicit prefixes override legacy matching of `alpha` or `beta` anywhere in warning text; otherwise `alpha` wins over `beta`. Deprecation uses `DEPRECATED` and takes precedence.
