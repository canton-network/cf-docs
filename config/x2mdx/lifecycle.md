# Lifecycle settings

Lifecycle labels in generated docs are an alpha feature. Please [share feedback](https://github.com/canton-network/cf-docs/issues).

## OpenAPI

```yaml
paths:
  /example:
    get:
      operationId: getExample
      x-state: alpha
      responses:
        '200':
          description: OK
```

Accepted values: `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## AsyncAPI

```yaml
channels:
  payments.created:
    x-state: alpha
    subscribe:
      x-state: beta
      message:
        payload:
          type: string
  payments.legacy:
    x-state: deprecated
```

Accepted `x-state` values: `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## OpenRPC

```json
{
  "methods": [{
    "name": "getExample",
    "x-state": "deprecated",
    "params": [],
    "result": {"name": "result", "schema": {"type": "string"}}
  }]
}
```

Accepted `x-state` values: `alpha`, `beta`, `stable`, `deprecated` (case-insensitive).

## TypeDoc

```ts
/** @alpha */
export interface Example {
  id: string;
}

/** @deprecated Use Example instead. */
export interface LegacyExample {
  id: string;
}
```

Accepted lifecycle tags: `@alpha`, `@beta`, `@stable`, `@deprecated`.

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

## JVM (Java and Scala 2.13)

```java
@Alpha
public class Example {
    @Beta public void preview() {}
    @Deprecated(since = "1.0.0") public void legacy() {}
}
```

```scala
@Alpha
class Example {
  @Beta def preview(): Unit = ()
  @deprecated("Use preview instead.", "1.0.0")
  def legacy(): Unit = ()
}
```

Accepted markers: `@Alpha`, `@Beta`, `@Stable`. Use Java `@Deprecated` or Scala `@deprecated` for deprecation.

Define/import the [marker annotations](../../tests/fixtures/jvm-lifecycle/annotations/example/lifecycle), annotate upstream source, and republish Javadoc/Scaladoc. Java markers require `@Documented`; no lifecycle YAML is needed.
