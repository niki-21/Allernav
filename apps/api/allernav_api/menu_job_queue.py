from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MenuRefreshMessage:
    version: int
    job_id: str
    place_id: str
    restaurant_name: str | None
    website_url: str
    document_urls: list[str]
    menu_version: str | None


def service_bus_menu_queue_configured() -> bool:
    return bool(os.getenv("AZURE_SERVICE_BUS_SEND_CONNECTION_STRING", "").strip())


def menu_queue_name() -> str:
    return os.getenv("AZURE_SERVICE_BUS_MENU_QUEUE", "menu-refresh").strip() or "menu-refresh"


def enqueue_menu_refresh(message: MenuRefreshMessage) -> None:
    connection_string = os.getenv("AZURE_SERVICE_BUS_SEND_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise RuntimeError("Azure Service Bus menu queue is not configured.")
    try:
        from azure.servicebus import ServiceBusClient, ServiceBusMessage
    except ImportError as exc:
        raise RuntimeError("azure-servicebus is not installed.") from exc

    client = ServiceBusClient.from_connection_string(connection_string)
    with client:
        sender = client.get_queue_sender(queue_name=menu_queue_name())
        with sender:
            sender.send_messages(
                ServiceBusMessage(
                    json.dumps(asdict(message)),
                    content_type="application/json",
                    message_id=message.job_id,
                )
            )


def parse_menu_refresh_message(payload: str | bytes) -> MenuRefreshMessage:
    raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    value = json.loads(raw)
    return MenuRefreshMessage(
        version=int(value.get("version", 1)),
        job_id=str(value["job_id"]),
        place_id=str(value["place_id"]),
        restaurant_name=value.get("restaurant_name"),
        website_url=str(value["website_url"]),
        document_urls=[str(url) for url in value.get("document_urls", [])],
        menu_version=value.get("menu_version"),
    )
