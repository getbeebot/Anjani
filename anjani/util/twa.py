"""
For Telegram Web App share link generating
"""
import msgpack
import base58
import os


class TWA:
    TWA_LINK = os.getenv("TWA_LINK")
    def __init__(self):
        pass

    @staticmethod
    def generate_project_detail_link(cls, project_id: int):
        args = msgpack.packb({
            "target": "projectDetail",
            "id": project_id,
        })
        args = base58.b58encode(args).decode("utf-8")
        return f"{cls.TWA_LINK}={args}"