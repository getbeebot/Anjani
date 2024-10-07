"""Anjani misc utils"""
# Copyright (C) 2020 - 2023  UserbotIndo Team, <https://github.com/userbotindo.git>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import shutil
from typing import TYPE_CHECKING, Any, Callable, Optional, Set, Tuple, Union

import base58
import msgpack
from aiopath import AsyncPath
from pyrogram.filters import AndFilter, Filter, InvertFilter, OrFilter

from anjani.util.types import CustomFilter

if TYPE_CHECKING:
    from anjani.core import Anjani

logger = logging.getLogger("misc")


def session_backup_sync():
    try:
        src = "anjani/anjani.session"
        dest = "session/anjani.latest.session"
        shutil.copy2(src, dest)
        logger.info("Session backed up successfully from %s to %s", src, dest)
    except shutil.SameFileError:
        logger.error("Souce and destination are the same file.")
    except OSError as e:
        logger.error("Error copying database file %s", e)


def session_restore_sync():
    try:
        src = "session/anjani.latest.session"
        dest = "anjani/anjani.session"
        shutil.copy2(src, dest)
        logger.info("Session restored successfully from %s to %s", src, dest)
    except shutil.SameFileError:
        logger.error("Souce and destination are the same file.")
    except OSError as e:
        logger.error("Error copying database file %s", e)


async def copy_file(src: AsyncPath, dest: AsyncPath):
    async with src.open(mode="rb") as s, dest.open(mode="wb") as d:
        while True:
            data = await s.read(4096)
            if not data:
                break
            await d.write(data)


async def session_backup_latest():
    session_dir = AsyncPath("session")
    if not await session_dir.exists():
        await session_dir.mkdir()
    src = AsyncPath("anjani/anjani.session")
    dest = AsyncPath("session/anjani.latest.session")
    await copy_file(src, dest)


async def session_backup():
    session_dir = AsyncPath("session")
    if not await session_dir.exists():
        await session_dir.mkdir()
    src = AsyncPath("anjani/anjani.session")
    dest = AsyncPath("session/anjani.session")
    await copy_file(src, dest)


async def session_restore():
    src = AsyncPath("session/anjani.latest.session")
    dest = AsyncPath("anjani/anjani.session")
    if not await src.exists():
        return
    await copy_file(src, dest)


def is_whitelist(chat_id) -> Optional[bool]:
    whitelist = [
        6812515288,
        1821086162,
        7465037644,
        2113937194,
        7037181285,
        1013334686,
        6303440178,
        7054195491,
    ]
    if chat_id in whitelist:
        return True

    return False


TWA_LINK = os.getenv("TWA_LINK")


def encode_args(args: dict) -> str:
    packed = msgpack.packb(args)
    return base58.b58encode(packed).decode("utf-8")


def decode_args(args_str: str) -> dict:
    p_args = base58.b58decode(args_str.encode("utf-8"))
    return msgpack.unpackb(p_args)


def generate_project_detail_link(project_id: int, bot_id: int):
    if project_id:
        payloads = {
            "target": "projectDetail",
            "id": int(project_id),
            "botid": int(bot_id),
        }
        args = encode_args(payloads)
        return f"{TWA_LINK}={args}"
    else:
        return TWA_LINK


def generate_task_detail_link(project_id: int, task_id: int, bot_id: int):
    if project_id:
        payloads = {
            "target": "taskShare",
            "id": int(project_id),
            "subid": int(task_id),
            "botid": int(bot_id),
        }
        args = encode_args(payloads)
        return f"{TWA_LINK}={args}"
    else:
        return TWA_LINK


def generate_luckydraw_link(project_id: int, task_id: int, bot_id: int):
    if project_id:
        payloads = {
            "target": "lotteryDetail",
            "id": int(project_id),
            "subid": int(task_id),
            "botid": int(bot_id),
        }
        args = encode_args(payloads)
        return f"{TWA_LINK}={args}"
    else:
        return TWA_LINK


def generate_project_leaderboard_link(project_id: int, bot_id: int):
    if project_id:
        payloads = {
            "target": "leaderBoard",
            "id": int(project_id),
            "botid": int(bot_id),
        }
        args = encode_args(payloads)
        return f"{TWA_LINK}={args}"
    else:
        return TWA_LINK


def generate_union_draw_portal_link(bot_id: int):
    payloads = {"target": "trafficExchange", "botid": int(bot_id)}
    args = encode_args(payloads)
    return f"{TWA_LINK}={args}"


def check_filters(filters: Union[Filter, CustomFilter], anjani: "Anjani") -> None:
    """Recursively check filters to set :obj:`~Anjani` into :obj:`~CustomFilter` if needed"""
    if isinstance(filters, (AndFilter, OrFilter, InvertFilter)):
        check_filters(filters.base, anjani)
    if isinstance(filters, (AndFilter, OrFilter)):
        check_filters(filters.other, anjani)

    # Only accepts CustomFilter instance
    if getattr(filters, "include_bot", False) and isinstance(filters, CustomFilter):
        filters.anjani = anjani


def find_prefixed_funcs(obj: Any, prefix: str) -> Set[Tuple[str, Callable[..., Any]]]:
    """Finds functions with symbol names matching the prefix on the given object."""

    results: Set[Tuple[str, Callable[..., Any]]] = set()

    for sym in dir(obj):
        if sym.startswith(prefix):
            name = sym[len(prefix) :]
            func = getattr(obj, sym)
            if not callable(func):
                continue

            results.add((name, func))

    return results


def do_nothing(*args: Any, **kwargs: Any) -> None:
    """Do nothing function"""
    return None


class StopPropagation(Exception):
    """Exception that raised to stop propagating an event"""
