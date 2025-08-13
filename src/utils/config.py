import json
import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

def fetch_peers_config() -> List[Dict[str, Any]]:
    """Uses a Lambda extension to fetch our peers.json configuration from AWS AppConfig.

    Raises:
        ValueError: for errors using the Lambda extension
        ValueError: if the config does not denote valid JSON

    Returns:
        List[Dict[str, Any]]: our peers.json configuration
    """
    if peers_config := os.environ.get("PEERS_JSON_UNDER_TEST"):  # tests might set this
        return json.loads(peers_config)
    else:
        url = _peers_config_url()
        logger.info(f"About to fetch peers.json using: {url}")

        try:
            response = requests.get(url=url)
            response.raise_for_status()
            return json.loads(response.text)
        except requests.HTTPError:
            logger.error("Unable to fetch peers.json")
            raise ValueError("Unable to fetch peers config.")
        except (ValueError, json.JSONDecodeError):
            logger.error("Config value fetched is invalid json")
            raise ValueError("Unable to process peers config.")
        

def fetch_configured_categories() -> List[Dict[str, str]]:
    """Returns a flattened list of configured categories for all peers from our peers.json configuration.

    Returns:
        List[Dict[str, str]]: flattened list of configured categories
    """
    categories = list()
    for peer in fetch_peers_config():
        for category in peer.get("categories", []):
           categories.append(
                {
                   "id": peer["id"], 
                   "category_id": category["category_id"], 
                   "filename_patterns": category["filename_patterns"],
                   "transformations": category.get("transformations", [])
                }
            )
    return categories

    
def _peers_config_url() -> str:
    return os.environ["APP_CONFIG_PEERS_URL"]
