import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import MessageService, MessageActionTopicEdit, \
    MessageActionTopicCreate, Message, MessageMediaDocument, DocumentAttributeFilename, \
    DocumentAttributeAudio

SESSIONS_DIR = "data/sessions"
DOWNLOADS_DIR = "data/downloads"
OFFSET_FILE = "offset.txt"

client = TelegramClient(
    os.path.join(SESSIONS_DIR, "account_session"),
    api_id=int(os.getenv('API_ID')),
    api_hash=os.getenv('API_HASH'),
)


async def retrieve_all_topics(group_id: int):
    supergroup = await client.get_input_entity(group_id)
    topic_map = {}
    async for message in client.iter_messages(supergroup):
        if not isinstance(message, MessageService):
            continue
        action = message.action
        if (isinstance(action, MessageActionTopicEdit)
                and message.reply_to.reply_to_msg_id not in topic_map):
            topic_map[message.reply_to.reply_to_msg_id] = action.title
            print(f"{message.reply_to.reply_to_msg_id} : {action.title}")
        if (isinstance(action, MessageActionTopicCreate)
                and message.id not in topic_map):
            topic_map[message.id] = action.title
            print(f"{message.id} : {action.title}")
    print(topic_map)


async def clone_messages_from_topic(group_id_from: int, topic_id_from: int | None , group_id_to: int, topic_id_to: int | None):
    base_path = os.path.join(DOWNLOADS_DIR, str(group_id_from), str(topic_id_from))
    os.makedirs(base_path, exist_ok=True)

    supergroup_from = await client.get_input_entity(group_id_from)
    supergroup_to = await client.get_input_entity(group_id_to)
    offset = load_offset(base_path)
    async for message in client.iter_messages(supergroup_from, reverse=True, min_id=offset, reply_to=topic_id_from):
        if not isinstance(message, Message):
            continue
        media = message.media
        if isinstance(media, MessageMediaDocument):
            message_path = os.path.join(base_path, str(message.id))
            os.makedirs(message_path, exist_ok=True)
            document = media.document
            filename_ = get_file_name(document.attributes)
            file_path = os.path.join(message_path, filename_)
            if (not os.path.exists(file_path)
                    or os.path.getsize(file_path) != document.size):
                print(f"Downloading file: {filename_}...")
                await client.download_media(media, file=file_path)
                print("Complete.")
            else:
                print(f"File by path {file_path}, already exists and matches destination size, skip.")
            print(f"Sending message: \n{message.text} \n\nwith attached file: \n{file_path}")

            await client.send_file(
                entity=supergroup_to,
                reply_to=topic_id_to,
                file=file_path,
                attributes=document.attributes,
                caption = message.text,
                voice_note=is_voice(document.attributes),
            )
        else:
            await client.send_message(
                entity=supergroup_to,
                reply_to=topic_id_to,
                message = message.text,
                parse_mode=None
            )
        offset = message.id
        persist_offset(base_path, offset)


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

with client:
    load_dotenv()
    group_id_from = get_env_var('GROUP_ID_FROM')
    topic_id_from = get_env_var('TOPIC_ID_FROM')
    group_id_to = get_env_var('GROUP_ID_TO')
    topic_id_to = get_env_var('TOPIC_ID_TO')

    if group_id_from is None or group_id_to is None:
        raise Exception("Missing env variable: GROUP_ID_FROM or GROUP_ID_TO")
    else:
        group_id_from = int(group_id_from)
        group_id_to = int(group_id_to)
    # client.loop.run_until_complete(retrieve_all_topics(group_id_from))
    client.loop.run_until_complete(clone_messages_from_topic(group_id_from, topic_id_from, group_id_to, topic_id_to))
