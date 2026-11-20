"""Entrypoint script to start the Chzzk Live platform client."""

import asyncio
import os
import sys
import traceback

from loguru import logger

# Add project root to sys.path to enable package imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from src.open_llm_vtuber.config_manager.utils import (  # noqa: E402
    read_yaml,
    validate_config,
)
from src.open_llm_vtuber.live.chzzk_live import ChzzkLivePlatform  # noqa: E402


async def main() -> None:
    """Load configuration and run the Chzzk Live platform client."""
    logger.info("Starting Chzzk Live platform client")

    try:
        config_path = os.path.join(project_root, "conf.yaml")
        config_data = read_yaml(config_path)
        config = validate_config(config_data)

        chzzk_config = config.live_config.chzzk_live
        if not chzzk_config.channel_id:
            logger.error(
                "No Chzzk channel_id specified in conf.yaml "
                "(live_config.chzzk_live.channel_id). "
                "Please set a 32-character Chzzk channel ID."
            )
            return

        logger.info(f"Connecting to Chzzk Live channel: {chzzk_config.channel_id}")

        platform = ChzzkLivePlatform(
            channel_id=chzzk_config.channel_id,
            proxy_url=chzzk_config.proxy_url,
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
