import logging
import os
from typing import Optional

import aiohttp


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
        self.log.info("Distribute join rewards request payloads: %s", payloads)

        rewards = None

        req_uri = f"{self.url_prefix}/p/task/bot-project/join"

        self.update_headers(payloads)
        self.headers.update({"Content-Type": "application/json"})

        async with self.http.put(
            url=req_uri, json=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Distribute join rewards response: %s", res)
                data = res.get("data")
                rewards = data.get("awardsDes") if data else None
            else:
                self.log.error("Distribute join rewards error: %s", await resp.text())

        return rewards

    async def create_project(self, payloads: dict) -> Optional[int]:
        self.log.info("Create project request payloads: %s", payloads)

        project_id = None
        tenant_id = None

        req_uri = f"{self.url_prefix}/p/task/bot-project/init"

        self.update_headers(payloads)
        self.headers.update({"Content-Type": "application/json"})

        async with self.http.put(
            url=req_uri, json=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Create project response: %s", res)
                data = res.get("data")
                if data:
                    project_id = int(data.get("id"))
                    tenant_id = int(data.get("tenantId") or 4)
            else:
                self.log.error("Create project error: %s", await resp.text())

        return (project_id, tenant_id)

    async def get_invite_link(self, payloads: dict) -> Optional[str]:
        self.log.info("Get invite link request payloads: %s", payloads)

        invite_link = None

        req_uri = f"{self.url_prefix}/p/distribution/code/getInviteLink"

        self.update_headers(payloads)

        async with self.http.get(
            url=req_uri, params=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Get invite link response: %s", res)
                invite_link = res.get("inviteLink")
            else:
                self.log.error("Get invite link error: %s", await resp.text())

        return invite_link

    async def checkin(self, payloads: dict) -> str:
        self.log.info("Checking request payloads: %s", payloads)

        ret = "Engage more, earn more."

        req_uri = f"{self.url_prefix}/p/task/bot-task/executeCommand"

        self.update_headers(payloads)
        self.headers.update({"Content-Type": "application/json"})

        async with self.http.post(
            url=req_uri, json=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Checkin response: %s", res)
                data = res.get("data")
                rewards = data.get("awardsDes")
                ret = f"Checkin successful, community points awarded: {rewards}"
            elif resp.status == 702:
                ret = "Already checked in"
            elif resp.status == 704:
                ret = "Sorry, there's no checkin task"
            else:
                self.log.error("Checkin unknow error: %s", await resp.text())

        return ret

    async def get_invite_log(self, payloads: dict) -> Optional[tuple]:
        self.log.info("Get invite log request payloads: %s", payloads)

        invited_number = None
        rewards = None
        reward_name = None

        req_uri = f"{self.url_prefix}/p/myWallet/getInviteLog"

        self.update_headers(payloads)

        async with self.http.get(
            url=req_uri, params=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Get invite log response: %s", res)

                invited_number = res.get("inviteNum")
                rewards = res.get("balance")
                reward_name = res.get("alias")
            else:
                self.log.error("Get invite log error: %s", await resp.text())

        return (invited_number, rewards, reward_name)

    async def get_ranks(self, payloads: dict):
        self.log.info("Get ranks request payloads: %s", payloads)

        req_uri = f"{self.url_prefix}/p/project/myRank"

        self.update_headers(payloads)

        async with self.http.get(
            url=req_uri, params=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Get ranks response: %s", res)
                return res.get("userRanks")
            else:
                self.log.error("Get ransk error: %s", await resp.text())

    async def add_admin(self, payloads: dict):
        self.log.info("Add admin request payloads: %s", payloads)

        req_uri = f"{self.url_prefix}/p/task/bot-project/addAdmin"

        self.update_headers(payloads)
        async with self.http.post(
            url=req_uri, json=payloads, headers=self.headers
        ) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Add admin response: %s", res)
                return res.get("data")
            else:
                self.log.error("Add admin error: %s", await resp.text())

    async def get_user_projects(self, payloads: dict):
        self.log.info("Get user projects request payloads: %s", payloads)

        user_id = payloads.get("user_id")

        req_uri = (
            f"{self.url_prefix}/p/task/bot-project/getProjectsManaged?userId={user_id}"
        )

        self.update_headers(payloads)

        async with self.http.get(url=req_uri, headers=self.headers) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Get user projects response: %s", res)
                data = res.get("data")
                projects = None
                if isinstance(data, list):
                    projects = [(i.get("id"), i.get("name")) for i in data]
                return projects
            else:
                self.log.error("Get user projects error: %s", await resp.text())

    async def get_project_res(self, payloads: dict):
        self.log.info("Get project res request payloads: %s", payloads)

        project_id = payloads.get("project_id")
        res_type = payloads.get("res_type")
        req_uri = f"{self.url_prefix}/p/task/bot-resource/getResourceByType?projectId={project_id}&type={res_type}"

        self.update_headers(payloads)

        async with self.http.get(url=req_uri, headers=self.headers) as resp:
            if resp.status == 200:
                res = await resp.json()
                self.log.info("Get project res response: %s", res)
                status = res.get("status") or 1
                items = res.get("itemList")
                desc = None
                pic = None
                text = None
                if isinstance(items, list) and len(items) >= 1:
                    pic = items[0].get("image") if items[0] else None
                    desc = items[0].get("description") if items[0] else None
                    text = items[0].get("text") if items[0] else None
                return (pic, status, desc, text)
            else:
                self.log.error("Get project pic error: %s", await resp.text())
                return (None, 1, None, None)
