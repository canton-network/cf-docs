# Lifecycle settings

Lifecycle labels in generated docs are an alpha feature. Please [share feedback](https://github.com/canton-network/cf-docs/issues).

`dev` hides an API until its latest observed version at or before the publish version has another label (or no label). Removal alone does not make a dev API public. Applies to OpenAPI operations, AsyncAPI channel actions, OpenRPC methods, Protobuf services, methods, messages, fields, enums, and enum values, TypeDoc exports, and Daml modules/functions.

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

```proto
// Creates a payment.
// @lifecycle alpha
rpc CreatePayment(CreatePaymentRequest) returns (Payment);

// @lifecycle deprecated
message LegacyPaymentRequest {
  // @lifecycle dev
  string internal_id = 2;
}
```

Put `@lifecycle <state>` on its own line in the leading comment of a service, rpc, message, field, enum, or enum value. The tag line is removed from the rendered description; the rest of the comment is kept. When several tag lines are present, the last one wins. A tag with an unrecognized value is left in the description unchanged. A `dev` service hides its rpcs unless they carry their own tag.

Accepted values: `dev`, `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

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
