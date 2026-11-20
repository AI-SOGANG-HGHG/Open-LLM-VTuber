"""Configuration models for live streaming platform integrations."""

from typing import ClassVar

from pydantic import Field

from .i18n import Description, I18nMixin


class BiliBiliLiveConfig(I18nMixin):
    """Configuration for BiliBili Live platform."""

    room_ids: list[int] = Field([], alias="room_ids")
    sessdata: str = Field("", alias="sessdata")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "room_ids": Description(
            en="List of BiliBili live room IDs to monitor",
            zh="要监控的B站直播间ID列表",
        ),
        "sessdata": Description(
            en="SESSDATA cookie value for authenticated requests (optional)",
            zh="用于认证请求的SESSDATA cookie值（可选）",
        ),
    }


class ChzzkLiveConfig(I18nMixin):
    """Configuration for Chzzk Live platform."""

    channel_id: str = Field("", alias="channel_id")
    proxy_url: str = Field("ws://localhost:12393/proxy-ws", alias="proxy_url")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "channel_id": Description(
            en="Chzzk channel ID (32-character hash from the channel URL)",
            zh="Chzzk频道ID（频道URL中的32位哈希值）",
        ),
        "proxy_url": Description(
            en="WebSocket URL of the local VTuber proxy endpoint",
            zh="本地VTuber代理端点的WebSocket URL",
        ),
    }


class LiveConfig(I18nMixin):
    """Configuration for live streaming platforms integration."""

    bilibili_live: BiliBiliLiveConfig = Field(
        BiliBiliLiveConfig(), alias="bilibili_live"
    )
    chzzk_live: ChzzkLiveConfig = Field(ChzzkLiveConfig(), alias="chzzk_live")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "bilibili_live": Description(
            en="Configuration for BiliBili Live platform",
            zh="B站直播平台配置",
        ),
        "chzzk_live": Description(
            en="Configuration for Chzzk Live platform",
            zh="Chzzk直播平台配置",
        ),
    }
