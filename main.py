import os
import re
import shutil
import traceback
from re import Pattern
from time import sleep

from dotenv import load_dotenv
from loguru import logger
from telethon import TelegramClient
from telethon.errors import FileReferenceExpiredError, FloodError
from telethon.tl.types import Message, MessageMediaDocument, DocumentAttributeFilename, \
    DocumentAttributeAudio, MessageMediaPoll, MessageMediaPhoto

from env_link_parser import load_link_pairs

SESSIONS_DIR = "data/sessions"
DOWNLOADS_DIR = "data/downloads"
OFFSET_FILE = "offset.txt"

client = TelegramClient(
    os.path.join(SESSIONS_DIR, "account_session"),
    api_id=int(os.getenv('API_ID')),
    api_hash=os.getenv('API_HASH'),
)


async def clone_messages_from_topic(group_id_from: int, topic_id_from: int | None , group_id_to: int, topic_id_to: int | None):
    base_path = os.path.join(DOWNLOADS_DIR, str(group_id_from), str(topic_id_from))
    os.makedirs(base_path, exist_ok=True)

    supergroup_from = await client.get_input_entity(group_id_from)
    supergroup_to = await client.get_input_entity(group_id_to)
    offset = load_offset(base_path)
    logger.info(f"Cloning from group {group_id_from} + topic {topic_id_from} into group {group_id_to} + topic {topic_id_to}")
    while True:
        init_offset = offset
        try:
            async for message in client.iter_messages(supergroup_from, reverse=True, min_id=offset, reply_to=topic_id_from, limit=50):
                if not isinstance(message, Message):
                    offset = message.id
                    continue
                logger.debug(f"Handling message https://t.me/c/{message.chat.id}/{message.id}")
                media = message.media
                match media:
                    case MessageMediaDocument():
                        await forward_media_document(base_path, media, message, supergroup_to, topic_id_to)
                    case MessageMediaPhoto():
                        await forward_photo(message, supergroup_to, topic_id_to)
                    case MessageMediaPoll():
                        logger.info(f"Skipping message with id {message.id}, because it has poll.")
                    case None:
                        await client.send_message(
                            entity=supergroup_to,
                            reply_to=topic_id_to,
                            message=message.text
                        )
                    case _:
                        logger.warning(f"Skipping message media, trying to send just text...")
                        await client.send_message(
                            entity=supergroup_to,
                            reply_to=topic_id_to,
                            message=message.text
                        )
                offset = message.id
                persist_offset(base_path, offset)
        except FileReferenceExpiredError:
            logger.warning(f"file from message with id {message.id} was expired, retry...")
            continue
        except FloodError as error:
            logger.error(error)
            if error.seconds:
                logger.info(f"Waiting {error.seconds} seconds before sending new messages...")
                sleep(error.seconds + 1)
            else:
                logger.warning(f"Unable to parse message: {error.message}, waiting 100 seconds...")
                sleep(100)
            continue
        except Exception as error:
            logger.error(error)
            traceback.print_exc()
            exit(1)
        if offset == init_offset:
            logger.info(f"Group {group_id_from} + topic {topic_id_from} was cloned successfully")
            logger.info(f"Cleanup of loaded data... (saving only offset)")
            shutil.rmtree(base_path)
            os.makedirs(base_path, exist_ok=True)
            persist_offset(base_path, offset)
            return


async def forward_media_document(base_path, media, message, supergroup_to, topic_id_to):
    message_path = os.path.join(base_path, str(message.id))
    os.makedirs(message_path, exist_ok=True)
    document = media.document
    filename_ = get_file_name(document.attributes)
    if re.search(FILE_IGNORE_PATTERN, filename_):
        logger.info(f"Skipping message with id {message.id}, as file ignore pattern matches")
        return
    file_path = os.path.join(message_path, filename_)
    if (not os.path.exists(file_path)
            or os.path.getsize(file_path) != document.size):
        logger.debug(f"Downloading file: {filename_}...")
        await client.download_media(media, file=file_path)
        logger.debug("Complete.")
    else:
        logger.debug(f"File by path {file_path}, already exists and matches destination size, skip.")
    text = text_cleanup(message.text)
    logger.debug(f"Sending message with id {message.id} \n\nwith attached file: {file_path}")
    await client.send_file(
        entity=supergroup_to,
        reply_to=topic_id_to,
        file=file_path,
        attributes=document.attributes,
        caption=text,
        voice_note=is_voice(document.attributes),
    )


async def forward_photo(message, supergroup_to, topic_id_to):
    image = await client.download_media(message.media, os.path.join(DOWNLOADS_DIR, "img"))
    msg_str = text_cleanup(message.text)
    logger.debug(f"Sending message with id {message.id} with attached photo")
    await client.send_message(
        entity=supergroup_to,
        reply_to=topic_id_to,
        file=image,
        message=msg_str
    )


async def load_message(group_id_from: int, topic_id_from: int | None, message_id):
    supergroup_from = await client.get_input_entity(group_id_from)
    async for message in client.iter_messages(supergroup_from, reverse=True, min_id=message_id - 1, reply_to=topic_id_from, limit=1):
        print(message)


def is_voice(attrs):
    resolved = [attr.voice for attr in attrs if isinstance(attr, DocumentAttributeAudio)]
    if resolved:
        return resolved[0]
    else:
        return False


def get_file_name(attrs):
    fnames = [attr.file_name for attr in attrs if isinstance(attr, DocumentAttributeFilename)]
    if fnames:
        return fnames[0]
    elif is_voice(attrs):
        return "voice.oga"
    else:
        return "No title.oga"


def persist_offset(base_path: str, offset: int):
    try:
        with open(os.path.join(base_path, OFFSET_FILE), 'w') as file:
            file.write(str(offset))
            return offset
    except ValueError:
        return 0
    except FileNotFoundError:
        return 0


def load_offset(base_path: str):
    try:
        with open(os.path.join(base_path, OFFSET_FILE), 'r') as file:
            number_str = file.read().strip()
            return int(number_str)
    except ValueError:
        return 0
    except FileNotFoundError:
        return 0


def get_env_var(var_name: str):
    value = os.getenv(var_name)
    if value is None or value == '':
        return None
    else:
        return int(value)


def text_cleanup(text: str):
    return re.sub(MESSAGE_CLEANUP_PATTERN, '', text)


def load_regexp_patterns_from_env() -> tuple[Pattern[str | None], Pattern[str | None]]:
    """
    Get regexp patterns from environment variables with fallback to defaults.
    Returns tuple of (file_ignore_pattern, message_cleanup_pattern)
    """

    # Get patterns from env or use defaults
    load_dotenv()
    file_ignore_pattern = os.getenv('FILE_IGNORE_PATTERN')
    message_cleanup_pattern = os.getenv('MESSAGE_CLEANUP_PATTERN')

    # Validate patterns by trying to compile them
    try:
        file_regex = re.compile(file_ignore_pattern, re.IGNORECASE)
        message_regex = re.compile(message_cleanup_pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"Invalid regular expression pattern: {e}")

    return file_regex, message_regex  # Now returning compiled regex objects


FILE_IGNORE_PATTERN, MESSAGE_CLEANUP_PATTERN = load_regexp_patterns_from_env()


# with client:
#     client.loop.run_until_complete(load_message(-1001750589044, None, 42))
    # client.loop.run_until_complete(clone_messages_from_topic(group_id_from, topic_id_from, group_id_to, topic_id_to))


with client:
    pairs = load_link_pairs()

    logger.info("Loaded Link pairs:")
    for i, pair in enumerate(pairs, 1):
        logger.info(f"{i}. {pair}")

    for pair in pairs:
        client.loop.run_until_complete(clone_messages_from_topic(pair.from_link.group_id, pair.from_link.topic_id, pair.to_link.group_id, pair.to_link.topic_id))
