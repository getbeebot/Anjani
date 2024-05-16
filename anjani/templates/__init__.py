from typing import AsyncIterator

from aiopath import AsyncPath
import yaml

async def get_template_files() -> AsyncIterator[AsyncPath]:
    async for language_file in AsyncPath("anjani/templates").iterdir():
        if language_file.suffix == ".yml":
            yield language_file

async def get_template(text: str, lang: str = "en") -> str:
    async for file in get_template_files():
        if str(file).endswith(f"{lang}.yml"):
            async with file.open(mode='r') as yaml_file:
                reader = await yaml_file.read()
                data = yaml.safe_load(reader)
                return data.get(text)