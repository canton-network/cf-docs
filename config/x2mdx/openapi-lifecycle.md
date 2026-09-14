# Mark an OpenAPI operation alpha or beta

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
