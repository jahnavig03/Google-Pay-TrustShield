"""Request-scoped access to the adapter set built at start-up."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .adapters import Services
from .ports import DocumentStore, Publisher, Translator


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def get_store(services: ServicesDep) -> DocumentStore:
    return services.store


def get_publisher(services: ServicesDep) -> Publisher:
    return services.publisher


StoreDep = Annotated[DocumentStore, Depends(get_store)]
PublisherDep = Annotated[Publisher, Depends(get_publisher)]


def get_translator(services: ServicesDep) -> Translator:
    return services.translator


TranslatorDep = Annotated[Translator, Depends(get_translator)]
