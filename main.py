import asyncio
import random

import aiohttp

from astrbot.api import logger
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from .blivedm import WebClient, OpenLiveClient
from .blivedm.models import message as bili_msg
from .context_rec import ContextRecord


@register("astrbot_plugin_bilibili_live", "Raven95676", "接入Bilibili直播", "0.1.0")
class BilibiliLive(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.web_client = None
        self.open_live_client = None
        if config["blivedm_web"]["enable"]:
            self.web_client = WebClient(
                config["blivedm_web"]["room_id"],
                cookie_str=config["blivedm_web"]["cookie_str"],
            )
        if config["blivedm_open_live"]["enable"]:
            self.open_live_client = OpenLiveClient(
                config["blivedm_open_live"]["access_key_id"],
                config["blivedm_open_live"]["access_key_secret"],
                config["blivedm_open_live"]["app_id"],
                config["blivedm_open_live"]["room_owner_auth_code"],
            )
        self.context_rec = ContextRecord(
            max_messages=config["plugin_settings"]["llm_chat_max_context"]
        )
        self.allow_message_type = {
            item.strip().lower()
            for item in self.config["plugin_settings"]["allow_message_type"].split(",")
        }
        self._process_task: asyncio.Task | None = None

    async def initialize(self):
        """初始化"""
        if self.web_client:
            self.web_client.start()
        elif self.open_live_client:
            self.open_live_client.start()
        self._process_task = asyncio.create_task(self._process_messages())

    async def _process_messages(self):
        """获取消息并处理"""
        if self.web_client:
            async for message in self.web_client.get_messages():
                await asyncio.sleep(0.8)
                await self._handle_message(message)
        elif self.open_live_client:
            async for message in self.open_live_client.get_messages():
                await asyncio.sleep(0.8)
                await self._handle_message(message)

    @staticmethod
    def _get_sender_id(message):
        """从消息中提取发送者ID"""
        return message.user_id if message.user_id != "0" else message.user_name

    async def _handle_message(self, message: bili_msg.BiliMessage):
        """处理消息分类"""
        if self.config["plugin_settings"]["random_drop"]["enable"]:
            if (
                random.random()
                < self.config["plugin_settings"]["random_drop"]["drop_rate"]
            ):
                logger.debug("Drop message")
                return

        sender = self._get_sender_id(message)

        if (
            isinstance(message, bili_msg.DanmakuMessage)
            and "danmaku" in self.allow_message_type
        ):
            await self._send_message(
                sender=sender,
                sender_name=message.user_name,
                message=f"[弹幕] {message.user_name}({message.user_id})说: {message.content}",
            )
        elif (
            isinstance(message, bili_msg.GiftMessage)
            and "gift" in self.allow_message_type
        ):
            await self._send_message(
                sender=sender,
                sender_name=message.user_name,
                message=f"[礼物] {message.user_name}({message.user_id})赠送了{message.gift_num}个{message.gift_name}",
            )
        elif (
            isinstance(message, bili_msg.SuperChatMessage)
            and "super_chat" in self.allow_message_type
        ):
            await self._send_message(
                sender=sender,
                sender_name=message.user_name,
                message=f"[醒目留言] {message.user_name}({message.user_id})说: {message.message}",
            )
        elif (
            isinstance(message, bili_msg.LikeMessage)
            and "like" in self.allow_message_type
        ):
            await self._send_message(
                sender=sender,
                sender_name=message.user_name,
                message=f"[点赞] {message.user_name}({message.user_id})点赞了",
            )
        elif (
            isinstance(message, bili_msg.EnterRoomMessage)
            and "enter_room" in self.allow_message_type
        ):
            await self._send_message(
                sender=sender,
                sender_name=message.user_name,
                message=f"[进入直播间] {message.user_name}({message.user_id})进入了直播间",
            )
        elif (
            isinstance(message, bili_msg.GuardBuyMessage)
            and "guard_buy" in self.allow_message_type
        ):
            guard_level_names = {1: "总督", 2: "提督", 3: "舰长"}
            guard_level_name = guard_level_names.get(message.guard_level, "未知")
            await self._send_message(
                sender=sender,
                sender_name=message.user_name,
                message=f"[上舰] {message.user_name}({message.user_id})成为了{guard_level_name}",
            )

    async def _send_llm_message(self, sender: str, message: str):
        """处理LLM聊天并更新上下文"""
        resp = await self.context.get_using_provider().text_chat(
            prompt=message,
            session_id=None,
            contexts=self.context_rec.get_messages(sender),
        )
        self.context_rec.put_message(sender, message, False)
        self.context_rec.put_message(sender, resp.result_chain.get_plain_text(), True)
        logger.debug(f"LLM Context: {self.context_rec.get_messages(sender)}")
        return resp

    async def _send_message(self, sender: str, sender_name: str, message: str):
        """发送消息"""
        logger.debug(f"bilibili_live message: {message}")
        work_mode = self.config["plugin_settings"]["work_mode"]

        if work_mode == "forward_only":
            for dest in self.config["plugin_settings"]["forward_destinations"]:
                await self.context.send_message(dest, MessageChain([Plain(message)]))
        elif work_mode == "llm_chat_forward":
            resp = await self._send_llm_message(sender, message)
            for dest in self.config["plugin_settings"]["forward_destinations"]:
                await self.context.send_message(dest, resp.result_chain)
        elif work_mode == "llm_chat_callback":
            method = self.config["plugin_settings"]["llm_chat_callback"][
                "callback_method"
            ]
            url = self.config["plugin_settings"]["llm_chat_callback"]["callback_url"]
            resp = await self._send_llm_message(sender, message)

            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    params = {
                        "sender": sender,
                        "sender_name": sender_name,
                        "message": resp.result_chain.get_plain_text(),
                    }
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            logger.error(
                                f"回调失败: {resp.status}, {await resp.text()}"
                            )
                else:
                    async with session.post(
                        url,
                        json={
                            "sender": sender,
                            "sender_name": sender_name,
                            "message": resp.result_chain.get_plain_text(),
                        },
                    ) as resp:
                        if resp.status != 200:
                            logger.error(
                                f"回调失败: {resp.status}, {await resp.text()}"
                            )

    async def terminate(self):
        """清理资源"""
        if self._process_task:
            self._process_task.cancel()
            try:
                await asyncio.wait_for(self._process_task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            finally:
                if self.web_client:
                    await self.web_client.stop_and_close()
                if self.open_live_client:
                    await self.open_live_client.stop_and_close()
