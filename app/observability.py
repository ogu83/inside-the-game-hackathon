"""App observability: Azure Monitor and OpenTelemetry tracing for agents, workflow, and Q&A."""

import logging
import os

log = logging.getLogger("observability")
_CONFIGURED = False


def init_observability() -> None:
    """Initialize OpenTelemetry tracing if configured via APPLICATIONINSIGHTS_CONNECTION_STRING or TRACING=foundry.

    Called once at app startup (FastAPI lifespan) and at the start of run_match.
    Never fails startup: logs a warning if initialization fails and continues.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    cs = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    tracing_mode = os.environ.get("TRACING", "").lower()

    if not cs and tracing_mode == "foundry":
        endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        if endpoint:
            try:
                from azure.ai.projects import AIProjectClient
                from app.agents.auth import get_shared_credential

                with AIProjectClient(endpoint=endpoint, credential=get_shared_credential()) as project:
                    cs = project.telemetry.get_application_insights_connection_string()
            except Exception as exc:
                log.warning("could not fetch telemetry connection string from Foundry: %s", exc)

    if not cs:
        return

    try:
        from agent_framework.observability import enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor

        sensitive = os.environ.get("TRACE_SENSITIVE", "0").lower() in ("1", "true", "yes")
        configure_azure_monitor(connection_string=cs)
        enable_instrumentation(enable_sensitive_data=sensitive)
        _CONFIGURED = True
        log.info("OpenTelemetry tracing configured with Azure Monitor (sensitive_data=%s)", sensitive)
    except Exception as exc:
        log.warning("failed to configure Azure Monitor tracing: %s", exc)


def flush_tracing() -> None:
    """Force flush all telemetry exporters if configured."""
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception as exc:
        log.debug("error flushing tracer provider: %s", exc)


def reset_observability() -> None:
    """Reset configuration flag for tests."""
    global _CONFIGURED
    _CONFIGURED = False


def is_observability_configured() -> bool:
    """Return whether observability has been configured."""
    return _CONFIGURED

