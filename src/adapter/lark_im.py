import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    Chat,
    ChatAnnouncement,
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateMessageResponse,
    DeleteMessageRequest,
    DeleteMessageResponse,
    EventMessage,
    ForwardMessageRequest,
    ForwardMessageRequestBody,
    ForwardMessageResponse,
    GetChatAnnouncementRequest,
    GetChatAnnouncementResponse,
    GetChatRequest,
    GetChatResponse,
    GetMessageRequest,
    GetMessageResourceRequest,
    GetMessageResourceResponse,
    GetMessageResponse,
    LinkChatRequest,
    LinkChatRequestBody,
    LinkChatResponse,
    ListChatRequest,
    ListChatResponse,
    ListMessageRequest,
    ListMessageResponse,
    MergeForwardMessageRequest,
    MergeForwardMessageRequestBody,
    MergeForwardMessageResponse,
    Message,
    PatchMessageRequest,
    PatchMessageRequestBody,
    PatchMessageResponse,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    ReplyMessageResponse,
)
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as WSClient

from src.config import PROJECT_ROOT
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MessageContent:
    content: str
    msg_type: str

    def __init__(self, content: str, msg_type: str) -> None:
        self.content = content
        self.msg_type = msg_type

    @staticmethod
    def text(text: str) -> "MessageContent":
        return MessageContent(json.dumps({"text": text}, ensure_ascii=False), "text")

    @staticmethod
    def post(post_content: Dict[str, Any]) -> "MessageContent":
        return MessageContent(json.dumps(post_content, ensure_ascii=False), "post")

    @staticmethod
    def image(image_key: str) -> "MessageContent":
        return MessageContent(json.dumps({"image_key": image_key}), "image")

    @staticmethod
    def file(file_key: str) -> "MessageContent":
        return MessageContent(json.dumps({"file_key": file_key}), "file")

    @staticmethod
    def card(card_content: Union[Dict[str, Any], List[Dict]]) -> "MessageContent":
        return MessageContent(json.dumps(card_content, ensure_ascii=False), "interactive")

    @staticmethod
    def interactive(card_content: Dict[str, Any]) -> "MessageContent":
        return MessageContent(json.dumps(card_content, ensure_ascii=False), "interactive")

    @staticmethod
    def share_chat(chat_id: str) -> "MessageContent":
        return MessageContent(json.dumps({"chat_id": chat_id}), "share_chat")

    @staticmethod
    def share_user(user_id: str) -> "MessageContent":
        return MessageContent(json.dumps({"user_id": user_id}), "share_user")

    @staticmethod
    def audio(file_key: str) -> "MessageContent":
        return MessageContent(json.dumps({"file_key": file_key}), "audio")

    @staticmethod
    def media(image_key: str, file_key: str) -> "MessageContent":
        return MessageContent(
            json.dumps({"image_key": image_key, "file_key": file_key}, ensure_ascii=False),
            "media",
        )

    @staticmethod
    def sticker(file_key: str) -> "MessageContent":
        return MessageContent(json.dumps({"file_key": file_key}), "sticker")


@dataclass
class SendMessageResult:
    message_id: str
    root_id: Optional[str] = None
    parent_id: Optional[str] = None
    msg_type: Optional[str] = None
    create_time: Optional[str] = None
    chat_id: Optional[str] = None
    content: Optional[str] = None
    sender: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None


@dataclass
class LarkIMConfig:
    app_id: str
    app_secret: str
    encrypt_key: str = ""
    verification_token: str = ""


class MessageEventHandler(Protocol):
    def __call__(self, event: P2ImMessageReceiveV1) -> Any:
        ...


class LarkIMClient:
    def __init__(self, config: LarkIMConfig) -> None:
        self._config = config
        self._client = lark.Client.builder() \
            .app_id(config.app_id) \
            .app_secret(config.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        self._ws_client: Optional[WSClient] = None
        self._event_handler: Optional[MessageEventHandler] = None
        self._ws_thread: Optional[threading.Thread] = None

    @property
    def client(self) -> lark.Client:
        return self._client

    # ==================== 发送消息 ====================

    def send_message(
        self,
        receive_id: str,
        msg_content: MessageContent,
        receive_id_type: str = "open_id",
        uuid: Optional[str] = None,
    ) -> SendMessageResult:
        body = CreateMessageRequestBody.builder() \
            .receive_id(receive_id) \
            .msg_type(msg_content.msg_type) \
            .content(msg_content.content) \
            .build()

        request_builder = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(body)

        if uuid is not None:
            request_builder.uuid(uuid)

        request = request_builder.build()
        response: CreateMessageResponse = self._client.im.v1.message.create(request)

        if not response.success():
            logger.error(
                "send_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"send_message failed: {response.msg} (code={response.code})")

        return self._parse_message_response(response.data)

    def send_text_message(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "open_id",
    ) -> SendMessageResult:
        return self.send_message(receive_id, MessageContent.text(text), receive_id_type)

    # ==================== 回复消息 ====================

    def reply_message(
        self,
        message_id: str,
        msg_content: MessageContent,
        uuid: Optional[str] = None,
    ) -> SendMessageResult:
        body = ReplyMessageRequestBody.builder() \
            .content(msg_content.content) \
            .msg_type(msg_content.msg_type) \
            .build()

        request_builder = ReplyMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(body)

        if uuid is not None:
            request_builder.uuid(uuid)

        request = request_builder.build()
        response: ReplyMessageResponse = self._client.im.v1.message.reply(request)

        if not response.success():
            logger.error(
                "reply_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"reply_message failed: {response.msg} (code={response.code})")

        return self._parse_message_response(response.data)

    # ==================== 编辑消息 ====================

    def edit_message(
        self,
        message_id: str,
        msg_content: MessageContent,
    ) -> SendMessageResult:
        body = PatchMessageRequestBody.builder() \
            .content(msg_content.content) \
            .build()
        body.msg_type = msg_content.msg_type

        request = PatchMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(body) \
            .build()

        response: PatchMessageResponse = self._client.im.v1.message.patch(request)

        if not response.success():
            logger.error(
                "edit_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"edit_message failed: {response.msg} (code={response.code})")

        return SendMessageResult(message_id=message_id, msg_type=msg_content.msg_type)

    # ==================== 转发消息 ====================

    def forward_message(
        self,
        message_id: str,
        receive_id: str,
        receive_id_type: str = "open_id",
        uuid: Optional[str] = None,
    ) -> SendMessageResult:
        body = ForwardMessageRequestBody.builder() \
            .receive_id(receive_id) \
            .build()

        request_builder = ForwardMessageRequest.builder() \
            .message_id(message_id) \
            .receive_id_type(receive_id_type) \
            .request_body(body)

        if uuid is not None:
            request_builder.uuid(uuid)

        request = request_builder.build()
        response: ForwardMessageResponse = self._client.im.v1.message.forward(request)

        if not response.success():
            logger.error(
                "forward_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"forward_message failed: {response.msg} (code={response.code})")

        return self._parse_message_response(response.data)

    # ==================== 合并转发消息 ====================

    def merge_forward_message(
        self,
        message_id_list: List[str],
        receive_id: str,
        receive_id_type: str = "open_id",
        uuid: Optional[str] = None,
    ) -> SendMessageResult:
        body = MergeForwardMessageRequestBody.builder() \
            .message_id_list(message_id_list) \
            .receive_id(receive_id) \
            .build()

        request_builder = MergeForwardMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(body)

        if uuid is not None:
            request_builder.uuid(uuid)

        request = request_builder.build()
        response: MergeForwardMessageResponse = self._client.im.v1.message.merge_forward(request)

        if not response.success():
            logger.error(
                "merge_forward_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"merge_forward_message failed: {response.msg} (code={response.code})")

        return self._parse_message_response(response.data)

    # ==================== 撤回消息 ====================

    def recall_message(self, message_id: str) -> None:
        request = DeleteMessageRequest.builder() \
            .message_id(message_id) \
            .build()

        response: DeleteMessageResponse = self._client.im.v1.message.delete(request)

        if not response.success():
            logger.error(
                "recall_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"recall_message failed: {response.msg} (code={response.code})")

    # ==================== 获取会话历史信息 ====================

    def get_conversation_history(
        self,
        container_id: str,
        container_id_type: str = "chat",
        page_size: int = 50,
        page_token: Optional[str] = None,
        sort_type: str = "ByCreateTimeDesc",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> ListMessageResponse:
        builder = ListMessageRequest.builder() \
            .container_id(container_id) \
            .container_id_type(container_id_type) \
            .page_size(page_size) \
            .sort_type(sort_type)

        if page_token is not None:
            builder.page_token(page_token)
        if start_time is not None:
            builder.start_time(start_time)
        if end_time is not None:
            builder.end_time(end_time)

        request = builder.build()
        response: ListMessageResponse = self._client.im.v1.message.list(request)

        if not response.success():
            logger.error(
                "get_conversation_history failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(
                f"get_conversation_history failed: {response.msg} (code={response.code})"
            )

        return response

    def get_all_conversation_history(
        self,
        container_id: str,
        container_id_type: str = "chat",
        page_size: int = 50,
        sort_type: str = "ByCreateTimeDesc",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Message]:
        all_messages: List[Message] = []
        page_token: Optional[str] = None

        while True:
            response = self.get_conversation_history(
                container_id=container_id,
                container_id_type=container_id_type,
                page_size=page_size,
                page_token=page_token,
                sort_type=sort_type,
                start_time=start_time,
                end_time=end_time,
            )

            if response.data is not None and response.data.items is not None:
                all_messages.extend(response.data.items)

            if response.data is not None and response.data.has_more is not None and response.data.has_more:
                page_token = response.data.page_token if response.data.page_token is not None else None
            else:
                break

        return all_messages

    # ==================== 获取消息中的资源文件 ====================

    def get_message_resource(
        self,
        message_id: str,
        file_key: str,
        resource_type: str = "file",
    ) -> GetMessageResourceResponse:
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type(resource_type) \
            .build()

        response: GetMessageResourceResponse = self._client.im.v1.message_resource.get(request)

        if not response.success():
            logger.error(
                "get_message_resource failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(
                f"get_message_resource failed: {response.msg} (code={response.code})"
            )

        return response

    def download_message_resource(
        self,
        message_id: str,
        file_key: str,
        resource_type: str = "file",
        output_dir: Optional[str] = None,
    ) -> str:
        response = self.get_message_resource(message_id, file_key, resource_type)

        if output_dir is None:
            output_dir = os.path.join(str(PROJECT_ROOT), "downloads")
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, file_key)
        with open(output_path, "wb") as f:
            if response.file is not None:
                f.write(response.file.read())

        logger.info("Resource downloaded to %s", output_path)
        return output_path

    # ==================== 获取特定消息内容 ====================

    def get_message(self, message_id: str) -> Message:
        request = GetMessageRequest.builder() \
            .message_id(message_id) \
            .build()

        response: GetMessageResponse = self._client.im.v1.message.get(request)

        if not response.success():
            logger.error(
                "get_message failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"get_message failed: {response.msg} (code={response.code})")

        if response.data is None or response.data.items is None or len(response.data.items) == 0:
            raise RuntimeError(f"get_message returned no data for message_id: {message_id}")

        return response.data.items[0]

    # ==================== 获取群分享链接 ====================

    def get_group_share_link(
        self,
        chat_id: str,
        validity_period: str = "week",
    ) -> str:
        body = LinkChatRequestBody.builder() \
            .validity_period(validity_period) \
            .build()

        request = LinkChatRequest.builder() \
            .chat_id(chat_id) \
            .request_body(body) \
            .build()

        response: LinkChatResponse = self._client.im.v1.chat.link(request)

        if not response.success():
            logger.error(
                "get_group_share_link failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(
                f"get_group_share_link failed: {response.msg} (code={response.code})"
            )

        if response.data is None or response.data.share_link is None:
            raise RuntimeError("get_group_share_link returned no share_link")

        return response.data.share_link

    # ==================== 获取群信息 ====================

    def get_group_info(self, chat_id: str) -> Chat:
        request = GetChatRequest.builder() \
            .chat_id(chat_id) \
            .build()

        response: GetChatResponse = self._client.im.v1.chat.get(request)

        if not response.success():
            logger.error(
                "get_group_info failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"get_group_info failed: {response.msg} (code={response.code})")

        if response.data is None:
            raise RuntimeError(f"get_group_info returned no data for chat_id: {chat_id}")

        return response.data

    def list_groups(
        self,
        page_size: int = 50,
        page_token: Optional[str] = None,
        sort_type: str = "ByActiveTimeDesc",
        user_id_type: str = "open_id",
    ) -> ListChatResponse:
        builder = ListChatRequest.builder() \
            .user_id_type(user_id_type) \
            .page_size(page_size) \
            .sort_type(sort_type)

        if page_token is not None:
            builder.page_token(page_token)

        request = builder.build()
        response: ListChatResponse = self._client.im.v1.chat.list(request)

        if not response.success():
            logger.error(
                "list_groups failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(f"list_groups failed: {response.msg} (code={response.code})")

        return response

    # ==================== 获取群公告消息 ====================

    def get_group_announcement(self, chat_id: str) -> ChatAnnouncement:
        request = GetChatAnnouncementRequest.builder() \
            .chat_id(chat_id) \
            .build()

        response: GetChatAnnouncementResponse = self._client.im.v1.chat_announcement.get(request)

        if not response.success():
            logger.error(
                "get_group_announcement failed, code: %s, msg: %s, log_id: %s",
                response.code, response.msg, response.get_log_id(),
            )
            raise RuntimeError(
                f"get_group_announcement failed: {response.msg} (code={response.code})"
            )

        if response.data is None:
            raise RuntimeError(f"get_group_announcement returned no data for chat_id: {chat_id}")

        return response.data

    # ==================== 长连接事件监听 ====================

    def set_event_handler(self, handler: MessageEventHandler) -> None:
        self._event_handler = handler

    def start_ws_listener(
        self,
        encrypt_key: str = "",
        verification_token: str = "",
        auto_reconnect: bool = True,
    ) -> None:
        if self._event_handler is None:
            raise RuntimeError("event_handler must be set before starting WS listener")

        event_dispatcher = EventDispatcherHandler.builder(
            encrypt_key or self._config.encrypt_key,
            verification_token or self._config.verification_token,
        ).register_p2_im_message_receive_v1(self._event_handler).build()

        self._ws_client = WSClient(
            app_id=self._config.app_id,
            app_secret=self._config.app_secret,
            log_level=lark.LogLevel.INFO,
            event_handler=event_dispatcher,
            auto_reconnect=auto_reconnect,
        )

        self._ws_thread = threading.Thread(target=self._ws_client.start, daemon=True)
        self._ws_thread.start()
        logger.info("WS listener started")

    def stop_ws_listener(self) -> None:
        self._ws_client = None
        self._ws_thread = None
        logger.info("WS listener stopped")

    # ==================== 内部工具方法 ====================

    @staticmethod
    def _parse_message_response(data: Any) -> SendMessageResult:
        if data is None:
            raise RuntimeError("message response data is None")

        message_id = getattr(data, "message_id", None)
        if message_id is None:
            raise RuntimeError("message response missing message_id")

        return SendMessageResult(
            message_id=message_id,
            root_id=getattr(data, "root_id", None),
            parent_id=getattr(data, "parent_id", None),
            msg_type=getattr(data, "msg_type", None),
            create_time=getattr(data, "create_time", None),
            chat_id=getattr(data, "chat_id", None),
            content=getattr(data, "content", None),
            sender=getattr(data, "sender", None),
            body=getattr(data, "body", None),
        )


def create_client_from_env() -> LarkIMClient:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    config = LarkIMConfig(
        app_id=os.environ.get("LARK_APP_ID", ""),
        app_secret=os.environ.get("LARK_APP_SECRET", ""),
        encrypt_key=os.environ.get("LARK_ENCRYPT_KEY", ""),
        verification_token=os.environ.get("LARK_VERIFICATION_TOKEN", ""),
    )

    if not config.app_id or not config.app_secret:
        raise RuntimeError(
            "LARK_APP_ID and LARK_APP_SECRET must be set in .env file"
        )

    return LarkIMClient(config)