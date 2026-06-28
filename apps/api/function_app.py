from __future__ import annotations

import logging

import azure.functions as func

from allernav_api.menu_job_queue import parse_menu_refresh_message
from allernav_api.menu_worker import process_menu_refresh_message


app = func.FunctionApp()


@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="%AZURE_SERVICE_BUS_MENU_QUEUE%",
    connection="AZURE_SERVICE_BUS_WORKER",
)
def process_menu_refresh(message: func.ServiceBusMessage) -> None:
    payload = parse_menu_refresh_message(message.get_body())
    attempt = int(getattr(message, "delivery_count", 1) or 1)
    logging.info("Processing menu refresh job %s (attempt %s)", payload.job_id, attempt)
    process_menu_refresh_message(payload, attempt=attempt)
