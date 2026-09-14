# Mark an OpenAPI operation alpha or beta

Set `x-state` on the operation in the upstream OpenAPI source:

```yaml
paths:
  /example:
    get:
      operationId: getExample
      x-state: alpha # or beta
      responses:
        '200':
          description: OK
```

Regenerate the reference docs. The operation page displays **Alpha** or **Beta**
beside its other badges. This works for JSON Ledger API and Splice OpenAPI pages.

Rendered examples: [Alpha](images/openapi-alpha.png) · [Beta](images/openapi-beta.png).

Use `stable` or omit `x-state` to show no prerelease badge. The displayed state
comes from the operation's published snapshot; earlier alpha/beta states do not
carry forward. Set it per operation, not on a path, schema, or the whole API.

Accepted values are `alpha`, `beta`, `stable`, and `deprecated` (case-insensitive).
Invalid values fail generation. This docs extension labels the API; it does not
change runtime behavior. Edit the upstream source, not generated MDX.
