import os
import aiohttp
import logging

from typing import Optional


class APIClient:
    url_prefix: str
    headers: dict
    http: aiohttp.ClientSession
    log: logging.Logger

    def __init__(self, prefix: str):
        self.url_prefix = prefix
        self.http = aiohttp.ClientSession()
        self.headers = {}
        self.log = logging.getLogger("Java API")

    @classmethod
    def init_from_env(cls):
        prefix = os.getenv("API_URL", "http://192.168.101.5:8112")
        client = cls(prefix)
        return client

    def update_headers(self, payloads: dict):
        bot_id = payloads.get("botId")
        if bot_id:
            self.headers.update({"Botid": str(bot_id)})

    async def distribute_join_rewards(self, payloads: dict) -> Optional[str]:
        self.log.debug("Distribute join rewards request payloads: %s", payloads)

        rewards = None

        req_uri = f"{self.url_prefix}/p/task/bot-project/join"

        self.update_headers(payloads)
        self.headers.update({"Content-Type": "application/json"})

        async with self.http.put(
            url=req_uri,
            json=payloads,
            headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.debug("Distribute join rewards response: %s", res)
                data = res.get("data")
                rewards = data.get("awardsDes") if data else None
            else:
               self.log.error("Distribute join rewards error: %s", await resp.text())

        if not self.http.closed:
            await self.http.close()

        return rewards

    async def create_project(self, payloads: dict) -> Optional[int]:
        self.log.debug("Create project request payloads: %s", payloads)

        project_id = None

        req_uri = f"{self.url_prefix}/p/task/bot-project/init"

        self.update_headers(payloads)
        self.headers.update({"Content-Type": "application/json"})

        async with self.http.put(
            url=req_uri,
            json=payloads,
            headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.debug("Create project response: %s", res)
                data = res.get("data")
                project_id = int(data.get("id")) if data else None
            else:
                self.log.error("Create project error: %s", await resp.text())

        if not self.http.closed:
            await self.http.close()

        return project_id

    async def get_invite_link(self, payloads: dict) -> Optional[str]:
        self.log.debug("Get invite link request payloads: %s", payloads)

        invite_link = None

        req_uri = f"{self.url_prefix}/p/distribution/code/getInviteLink"

        self.update_headers(payloads)

        async with self.http.get(
            url=req_uri,
            params=payloads,
            headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.debug("Get invite link response: %s", res)
                invite_link = res.get("inviteLink")
            else:
                self.log.error("Get invite link error: %s", await resp.text())

        if not self.http.closed:
            await self.http.close()

        return invite_link

    async def checkin(self, payloads: dict) -> str:
        self.log.debug("Checking request payloads: %s", payloads)

        ret = "Engage more, earn more."

        req_uri = f"{self.url_prefix}/p/task/bot-task/executeCommand"

        self.update_headers(payloads)
        self.headers.update({"Content-Type": "application/json"})

        async with self.http.post(
            url=req_uri,
            json=payloads,
            headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.debug("Checkin response: %s", res)
                data = res.get("data")
                rewards = data.get("awardsDes")
                ret = f"Checkin successful, community points awarded: {rewards}"
            elif resp.status == 702:
                ret = "Already checked in"
            elif resp.status == 704:
                ret = "Sorry, there's no checkin task"
            else:
                self.log.error("Checkin unknow error: %s", await resp.text())

        if not self.http.closed:
            await self.http.close()

        return ret

    async def get_invite_log(self, payloads: dict) -> Optional[tuple]:
        self.log.debug("Get invite log request payloads: %s", payloads)

        invited_number = None
        rewards = None
        reward_name = None

        req_uri = f"{self.url_prefix}/p/myWallet/getInviteLog"

        self.update_headers(payloads)

        async with self.http.get(
            url=req_uri,
            params=payloads,
            headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.debug("Get invite log response: %s", res)

                invited_number = res.get("inviteNum")
                rewards = res.get("balance")
                reward_name = res.get("alias")
            else:
                self.log.error("Get invite log error: %s", await resp.text())

        if not self.http.closed:
            await self.http.close()

        return (invited_number, rewards, reward_name)