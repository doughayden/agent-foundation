# Cloud Run environment variables per environment, merged over the template wiring in main.tf.
# An entry here wins over a template-set key of the same name. Plain values only: keep secrets out.
# OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT is required in every environment; NO_CONTENT also
# sets ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false. Guide: docs/environment-variables.md.
locals {
  run_app_env_config = {
    dev = {
      ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS         = "TRUE"
      LOG_LEVEL                                          = "INFO"
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "SPAN_AND_EVENT"
      SERVE_WEB_INTERFACE                                = "FALSE"
    }
    stage = {
      ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS         = "TRUE"
      LOG_LEVEL                                          = "INFO"
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "NO_CONTENT"
      SERVE_WEB_INTERFACE                                = "FALSE"
    }
    prod = {
      ADK_SUPPRESS_EXPERIMENTAL_FEATURE_WARNINGS         = "TRUE"
      LOG_LEVEL                                          = "INFO"
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "NO_CONTENT"
      SERVE_WEB_INTERFACE                                = "FALSE"
    }
  }
}
