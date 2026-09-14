package example.api;
import example.lifecycle.*;

/** Example Java API. */
@Alpha
public class Example {
    @Beta public void preview() {}
    @Stable public void released() {}
    @Deprecated(since = "1.0.0") public void legacy() {}
    /** Mentioning @Alpha in prose does not annotate this method. */
    public void unmarked() {}
}
