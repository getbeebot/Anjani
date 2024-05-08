from typing import ClassVar

from anjani import command, plugin


class RepeaterPlugin(plugin.Plugin):
    name: ClassVar[str] = "Repeater Plugin"
    helpable: ClassVar[bool] = True

    async def cmd_hi(self, ctx: command.Context) -> None:
        await ctx.respond("hola")
