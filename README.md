# astrbot_plugin_bilibili_live

> [!note]
> umo即sid，可以通过`/sid`命令获取。
>
> 本项目所使用的blivedm经过二次开发，如有问题请勿直接向原作者提交issue。

## 简介
AstrBot B站直播插件用于接入 Bilibili 直播，支持 **Web 接入** 和 **开放平台接入** 两种方式，可接收直播间的弹幕、礼物、醒目留言、点赞、进入直播间和上舰等消息。

## 功能特性
- 支持 **Web 接入** 和 **开放平台接入**
- 接收多种直播间消息类型：
    - 实时弹幕 (danmaku)
    - 礼物赠送 (gift)
    - 醒目留言 (super_chat)
    - 点赞 (like)
    - 进场 (enter_room)
    - 上舰通知 (guard_buy)
- 支持三种工作模式：
  - **仅转发模式**：直接将直播间消息转发到指定目标
  - **LLM 聊天并转发模式**：将消息发送给 LLM 处理后转发
  - **LLM 聊天并回调模式**：将消息发送给 LLM 处理后通过回调接口发送
- 支持上下文记录
- 支持随机丢弃消息

## 回调格式

```json
{
    "sender": "发送者ID",
    "sender_name": "发送者昵称",
    "message": "消息文本"
}
```