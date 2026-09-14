# JVM annotation examples

`annotations/` contains reusable Java marker definitions; both `java/` and `scala/` import them. These are example definitions, not a published annotation dependency.

Generate Javadoc and Scala 2.13 Scaladoc, package their HTML into jars, and verify the converted pages:

```sh
direnv exec . env JVM_EXAMPLE_OUTPUT=/tmp/jvm-lifecycle python3 -m pytest tests/test_jvm_source_annotations.py -q
```

Generated HTML is in `/tmp/jvm-lifecycle/java-docs` and `scala-docs`; generated MDX is in `/tmp/jvm-lifecycle/site`. The test verifies type and method labels, native deprecation, stable/unmarked declarations, and ignores marker names in prose.

Upstream projects must define or import the markers, annotate source, and republish their documentation archives. Java markers need `@Documented`. No doclet, compiler plugin, or lifecycle manifest mapping is required. The existing production acquisition wrapper currently selects Java artifacts only.
