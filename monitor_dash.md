What Phoenix can monitor

If your LLM calls are instrumented correctly (for example via OpenInference/OpenTelemetry instrumentation), Phoenix Cloud can show:

Metric	Supported	Notes
Prompt	✅	Full prompt sent to the model (if not redacted)
Completion	✅	Model response
Input tokens	✅	If reported by the provider or instrumentation
Output tokens	✅	If available
Total tokens	✅	Derived from usage metadata
Latency	✅	End-to-end response time
Trace hierarchy	✅	Entire request lifecycle
Span timing	✅	Every operation duration
Errors	✅	Exceptions and failed calls
Model name	✅	GPT-4.1, GPT-5, Claude, etc.
Temperature	✅	If included in span attributes
User/session/project IDs	✅	Via custom span attributes
