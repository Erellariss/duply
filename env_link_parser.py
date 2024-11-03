import os
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

from dotenv import load_dotenv


class LinkValidationError(Exception):
    """Custom exception for link validation errors"""
    pass


@dataclass
class TelegramLink:
    """Data class to store Telegram message information"""
    group_id: int
    topic_id: Optional[int]

    def __str__(self) -> str:
        if self.topic_id is not None:
            return f"{self.group_id}/{self.topic_id}"
        return str(self.group_id)


@dataclass
class LinkPair:
    """Data class to store a pair of Telegram messages (from -> to)"""
    from_link: TelegramLink
    to_link: TelegramLink

    def __str__(self) -> str:
        return f"{self.from_link} -> {self.to_link}"


def parse_telegram_link(link: str) -> TelegramLink:
    """
    Parse a Telegram link to extract group ID and optional topic ID.

    Args:
        link (str): Telegram link like "https://t.me/c/178237449432/35664" or "https://t.me/c/20323289223431"

    Returns:
        TelegramLink: Object containing group_id and topic_id as integers
    """
    # Clean the link by removing trailing slashes and whitespace
    link = link.strip().rstrip('/')

    # Use regex to extract the IDs
    pattern = r'(-?\d+)(?:[\/_](-?\d+))?'
    match = re.search(pattern, link)

    if not match:
        raise ValueError(f"Invalid Telegram link format: {link}")

    # Convert IDs to integers
    group_id = int(match.group(1))
    topic_id = int(match.group(2)) if match.group(2) else None

    return TelegramLink(group_id, topic_id)


def validate_link_counts(from_links: List[str], to_links: List[str]) -> None:
    """
    Validate that the number of links in both lists matches.

    Args:
        from_links (List[str]): List of source links
        to_links (List[str]): List of destination links

    Raises:
        LinkValidationError: If the number of links doesn't match
    """
    if len(from_links) != len(to_links) or len(from_links) == 0:
        raise LinkValidationError(
            f"Number of links doesn't match: 'from' has {len(from_links)} links, "
            f"'to' has {len(to_links)} links"
        )

    if len(from_links) == 0:
        raise LinkValidationError("No links found in environment variables")


def get_telegram_links_from_env() -> Tuple[List[str], List[str]]:
    """
    Read and validate Telegram links from environment variables 'from' and 'to'.

    Returns:
        Tuple[List[str], List[str]]: Two lists containing 'from' and 'to' links
    """
    load_dotenv()
    # Get environment variables and split by comma
    from_links = os.getenv('FROM', '').split(',')
    to_links = os.getenv('TO', '').split(',')

    # Clean empty strings and whitespace
    from_links = [link.strip() for link in from_links if link.strip()]
    to_links = [link.strip() for link in to_links if link.strip()]

    # Validate link counts
    validate_link_counts(from_links, to_links)

    return from_links, to_links


def load_link_pairs() -> List[LinkPair]:
    """
    Create pairs of Telegram messages from environment variables.

    Returns:
        List[LinkPair]: List of paired messages (from -> to)
    """
    from_links, to_links = get_telegram_links_from_env()

    # Parse all links and create pairs
    message_pairs = [
        LinkPair(
            from_link=parse_telegram_link(from_link),
            to_link=parse_telegram_link(to_link)
        )
        for from_link, to_link in zip(from_links, to_links)
    ]

    return message_pairs