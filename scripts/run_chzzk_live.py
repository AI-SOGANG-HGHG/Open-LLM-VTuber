"""Entrypoint script to start the Chzzk Live platform client."""

import asyncio
import os
import sys
import traceback
from urllib.parse import urlsplit

from loguru import logger

# Add project root to sys.path to enable package imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from src.open_llm_vtuber.config_manager.live import LiveConfig  # noqa: E402
from src.open_llm_vtuber.config_manager.utils import read_yaml  # noqa: E402
from src.open_llm_vtuber.live.chzzk_live import ChzzkLivePlatform  # noqa: E402
from src.open_llm_vtuber.studio_auth import CHZZK_COLLECTOR_PATH  # noqa: E402


async def main() -> None:
    """Load configuration and run the Chzzk Live platform client."""
    logger.info("Starting Chzzk Live platform client")

    try:
        config_path = os.path.join(project_root, "conf.yaml")
        config_data = read_yaml(config_path)
        chzzk_config = LiveConfig.model_validate(
            config_data.get("live_config", {})
        ).chzzk_live
        if not chzzk_config.channel_id:
            logger.error(
                "No Chzzk channel_id specified in conf.yaml "
                "(live_config.chzzk_live.channel_id). "
                "Please set a 32-character Chzzk channel ID."
            )
            return

        logger.info(f"Connecting to Chzzk Live channel: {chzzk_config.channel_id}")

        proxy = urlsplit(chzzk_config.proxy_url)
        collector_token = ""
        if proxy.path == CHZZK_COLLECTOR_PATH:
            collector_token = os.getenv("STUDIO_CHZZK_TOKEN", "")
            if (
                proxy.scheme != "ws"
                or proxy.hostname not in {"127.0.0.1", "::1"}
                or proxy.username is not None
                or not collector_token
            ):
                logger.error(
                    "Configure a loopback collector URL and STUDIO_CHZZK_TOKEN"
                )
                return
        platform = ChzzkLivePlatform(
            channel_id=chzzk_config.channel_id,
            proxy_url=chzzk_config.proxy_url,
            collector_token=collector_token,
        )
        await platform.run()

    except Exception as e:
        logger.error(f"Error starting Chzzk Live client: {e}")
        logger.debug(traceback.format_exc())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down Chzzk Live platform")
