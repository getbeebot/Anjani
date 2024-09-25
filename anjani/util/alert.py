import base64
import logging
import os

import aiohttp

log = logging.getLogger("Alert")


async def send_alert(name: str, description: str, level: str = "info") -> None:
    alert_msg = {
        "status": "firing",
        "labels": {
            "alertname": name,
            "severity": level,
            "alert_type": "app",
            "instance": "anjani",
        },
        "annotations": {"description": description},
    }

    url = os.getenv("ALERT_API")
    user = os.getenv("ALERT_USER")
    password = os.getenv("ALERT_PASS")

    auth_token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
    auth = f"Basic {auth_token}"
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
    }
    payloads = [alert_msg]
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payloads, headers=headers) as resp:
            if resp.status == 200:
                log.info("Sent alert %s success", payloads)
            else:
                log.warning(
                    "Sent alert %s failed, error: %s", payloads, await resp.text()
                )
