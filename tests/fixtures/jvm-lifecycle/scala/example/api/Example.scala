package example.api
import example.lifecycle.{Alpha, Beta, Stable}

/** Experimental Scala API. */
@Alpha
class Example {
  @Beta def preview(): Unit = ()
  @Stable def released(): Unit = ()
  @deprecated("Use preview instead.", "1.0.0")
  def legacy(): Unit = ()
  /** Mentioning @Alpha in prose does not annotate this method. */
  def unmarked(): Unit = ()
}
@Beta class Preview
@Stable class Released
@deprecated("Use Example instead.", "1.0.0") class Legacy
class Unmarked
