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
