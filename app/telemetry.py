import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.settings import Settings

logger = logging.getLogger(__name__)


def setup_telemetry(app: FastAPI, settings: Settings) -> None:
    """Трассировка поднимается только при указанном коллекторе.

    Без адреса экспортёр копил бы спаны и раз в интервал пытался их
    отправить в никуда, поэтому по умолчанию трассировки нет вовсе.
    """
    if not settings.otel_exporter_otlp_endpoint:
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=(f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
            )
        )
    )
    trace.set_tracer_provider(provider)

    # Инструментация вешается на приложение до первого запроса и
    # исключает операционные адреса: трасса запроса от оркестратора или
    # сборщика метрик ничего не говорит о работе API.
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="health,metrics", tracer_provider=provider
    )
    logger.info("tracing enabled")
