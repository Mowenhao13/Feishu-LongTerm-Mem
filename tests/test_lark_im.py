import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from src.adapter.lark_im import (
    LarkIMClient,
    LarkIMConfig,
    MessageContent,
    MessageEventHandler,
    SendMessageResult,
    create_client_from_env,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@pytest.fixture
def mock_client() -> LarkIMClient:
    config = LarkIMConfig(
        app_id="test_app_id",
        app_secret="test_app_secret",
    )
    return LarkIMClient(config)


@pytest.fixture
def mock_send_message_data() -> Dict[str, Any]:
    return {
        "message_id": "om_abc123",
        "root_id": "om_root456",
        "parent_id": "om_parent789",
        "msg_type": "text",
        "create_time": "1710000000",
        "chat_id": "oc_test_chat",
        "content": json.dumps({"text": "hello"}),
        "sender": {"id": "ou_sender", "id_type": "open_id"},
        "body": {"content": "hello"},
    }


# ==================== MessageContent Tests ====================


class TestMessageContent:
    def test_text(self) -> None:
        mc = MessageContent.text("你好世界")
        assert mc.msg_type == "text"
        assert json.loads(mc.content) == {"text": "你好世界"}

    def test_image(self) -> None:
        mc = MessageContent.image("img_key_123")
        assert mc.msg_type == "image"
        assert json.loads(mc.content) == {"image_key": "img_key_123"}

    def test_file(self) -> None:
        mc = MessageContent.file("file_key_456")
        assert mc.msg_type == "file"
        assert json.loads(mc.content) == {"file_key": "file_key_456"}

    def test_interactive(self) -> None:
        card = {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "hello"}}]}
        mc = MessageContent.interactive(card)
        assert mc.msg_type == "interactive"
        assert json.loads(mc.content) == card

    def test_post(self) -> None:
        post_content = {"zh_cn": {"title": "title", "content": [[{"tag": "text", "text": "hello"}]]}}
        mc = MessageContent.post(post_content)
        assert mc.msg_type == "post"

    def test_share_chat(self) -> None:
        mc = MessageContent.share_chat("oc_test_chat")
        assert mc.msg_type == "share_chat"
        assert json.loads(mc.content) == {"chat_id": "oc_test_chat"}

    def test_share_user(self) -> None:
        mc = MessageContent.share_user("ou_test_user")
        assert mc.msg_type == "share_user"
        assert json.loads(mc.content) == {"user_id": "ou_test_user"}

    def test_audio(self) -> None:
        mc = MessageContent.audio("audio_key_789")
        assert mc.msg_type == "audio"
        assert json.loads(mc.content) == {"file_key": "audio_key_789"}

    def test_media(self) -> None:
        mc = MessageContent.media("img_key", "file_key")
        assert mc.msg_type == "media"
        assert json.loads(mc.content) == {"image_key": "img_key", "file_key": "file_key"}

    def test_sticker(self) -> None:
        mc = MessageContent.sticker("sticker_key")
        assert mc.msg_type == "sticker"
        assert json.loads(mc.content) == {"file_key": "sticker_key"}


# ==================== LarkIMClient Tests ====================


class TestSendMessage:
    def test_send_text_message_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.message_id = "om_test_123"
        mock_response.data.root_id = None
        mock_response.data.parent_id = None
        mock_response.data.msg_type = "text"
        mock_response.data.create_time = "1710000000"
        mock_response.data.chat_id = "oc_test"
        mock_response.data.content = json.dumps({"text": "hello"})
        mock_response.data.sender = None
        mock_response.data.body = None
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_123"

        with patch.object(
            mock_client.client.im.v1.message, "create", return_value=mock_response
        ) as mock_create:
            result = mock_client.send_text_message("ou_receiver", "你好世界")

            assert result.message_id == "om_test_123"
            assert result.msg_type == "text"
            mock_create.assert_called_once()

    def test_send_message_failure(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 99999
        mock_response.msg = "permission denied"
        mock_response.get_log_id.return_value = "log_err"

        with patch.object(
            mock_client.client.im.v1.message, "create", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="permission denied"):
                mock_client.send_text_message("ou_receiver", "hello")


class TestReplyMessage:
    def test_reply_message_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.message_id = "om_reply_123"
        mock_response.data.msg_type = "text"
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_reply"

        with patch.object(
            mock_client.client.im.v1.message, "reply", return_value=mock_response
        ) as mock_reply:
            result = mock_client.reply_message("om_original", MessageContent.text("回复消息"))

            assert result.message_id == "om_reply_123"
            mock_reply.assert_called_once()

    def test_reply_message_failure(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 10003
        mock_response.msg = "message not found"
        mock_response.get_log_id.return_value = "log_err"

        with patch.object(
            mock_client.client.im.v1.message, "reply", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="message not found"):
                mock_client.reply_message("om_invalid", MessageContent.text("test"))


class TestEditMessage:
    def test_edit_message_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_edit"

        with patch.object(
            mock_client.client.im.v1.message, "patch", return_value=mock_response
        ) as mock_patch:
            result = mock_client.edit_message("om_original", MessageContent.text("编辑后内容"))

            assert result.message_id == "om_original"
            mock_patch.assert_called_once()


class TestForwardMessage:
    def test_forward_message_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.message_id = "om_fwd_123"
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_fwd"

        with patch.object(
            mock_client.client.im.v1.message, "forward", return_value=mock_response
        ) as mock_forward:
            result = mock_client.forward_message("om_original", "ou_target")

            assert result.message_id == "om_fwd_123"
            mock_forward.assert_called_once()


class TestMergeForwardMessage:
    def test_merge_forward_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.message_id = "om_merge_123"
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_merge"

        with patch.object(
            mock_client.client.im.v1.message, "merge_forward", return_value=mock_response
        ) as mock_merge:
            result = mock_client.merge_forward_message(
                ["om_1", "om_2", "om_3"], "ou_target"
            )

            assert result.message_id == "om_merge_123"
            mock_merge.assert_called_once()


class TestRecallMessage:
    def test_recall_message_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_recall"

        with patch.object(
            mock_client.client.im.v1.message, "delete", return_value=mock_response
        ) as mock_delete:
            mock_client.recall_message("om_to_recall")

            mock_delete.assert_called_once()

    def test_recall_message_failure(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 10003
        mock_response.msg = "message not found"
        mock_response.get_log_id.return_value = "log_err"

        with patch.object(
            mock_client.client.im.v1.message, "delete", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="message not found"):
                mock_client.recall_message("om_invalid")


class TestGetConversationHistory:
    def test_get_conversation_history_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.items = []
        mock_response.data.has_more = False
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_list"

        with patch.object(
            mock_client.client.im.v1.message, "list", return_value=mock_response
        ) as mock_list:
            response = mock_client.get_conversation_history("oc_test_chat")

            assert response.success()
            mock_list.assert_called_once()

    def test_get_conversation_history_failure(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 99999
        mock_response.msg = "internal error"
        mock_response.get_log_id.return_value = "log_err"

        with patch.object(
            mock_client.client.im.v1.message, "list", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="internal error"):
                mock_client.get_conversation_history("oc_invalid")

    def test_get_all_conversation_history(self, mock_client: LarkIMClient) -> None:
        mock_message_1 = MagicMock()
        mock_message_1.message_id = "om_1"
        mock_message_2 = MagicMock()
        mock_message_2.message_id = "om_2"

        mock_response_page1 = MagicMock()
        mock_response_page1.success.return_value = True
        mock_response_page1.data.items = [mock_message_1]
        mock_response_page1.data.has_more = True
        mock_response_page1.data.page_token = "token_next"
        mock_response_page1.code = 0
        mock_response_page1.get_log_id.return_value = "log1"

        mock_response_page2 = MagicMock()
        mock_response_page2.success.return_value = True
        mock_response_page2.data.items = [mock_message_2]
        mock_response_page2.data.has_more = False
        mock_response_page2.code = 0
        mock_response_page2.get_log_id.return_value = "log2"

        with patch.object(
            mock_client.client.im.v1.message, "list",
            side_effect=[mock_response_page1, mock_response_page2],
        ):
            messages = mock_client.get_all_conversation_history("oc_test_chat")

            assert len(messages) == 2
            assert messages[0].message_id == "om_1"
            assert messages[1].message_id == "om_2"


class TestGetMessage:
    def test_get_message_success(self, mock_client: LarkIMClient) -> None:
        mock_message = MagicMock()
        mock_message.message_id = "om_get_123"
        mock_message.msg_type = "text"
        mock_message.content = json.dumps({"text": "hello"})

        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.items = [mock_message]
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_get"

        with patch.object(
            mock_client.client.im.v1.message, "get", return_value=mock_response
        ) as mock_get:
            message = mock_client.get_message("om_get_123")

            assert message.message_id == "om_get_123"
            assert message.msg_type == "text"
            mock_get.assert_called_once()

    def test_get_message_no_data(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.items = []
        mock_response.code = 0
        mock_response.get_log_id.return_value = "log_get"

        with patch.object(
            mock_client.client.im.v1.message, "get", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="no data"):
                mock_client.get_message("om_empty")


class TestGetMessageResource:
    def test_get_message_resource_success(self, mock_client: LarkIMClient) -> None:
        mock_file = MagicMock()
        mock_file.read.return_value = b"fake_file_content"

        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.file = mock_file
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_resource"

        with patch.object(
            mock_client.client.im.v1.message_resource, "get", return_value=mock_response
        ) as mock_resource_get:
            response = mock_client.get_message_resource("om_msg", "file_key_123", "file")

            assert response.success()
            mock_resource_get.assert_called_once()

    def test_get_message_resource_failure(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 99999
        mock_response.msg = "resource not found"
        mock_response.get_log_id.return_value = "log_err"

        with patch.object(
            mock_client.client.im.v1.message_resource, "get", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="resource not found"):
                mock_client.get_message_resource("om_msg", "invalid_key")

    def test_download_message_resource(self, mock_client: LarkIMClient, tmp_path: Path) -> None:
        mock_file = MagicMock()
        mock_file.read.return_value = b"binary_data"

        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.file = mock_file
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_dl"

        with patch.object(
            mock_client.client.im.v1.message_resource, "get", return_value=mock_response
        ):
            output_path = mock_client.download_message_resource(
                "om_msg", "dl_file_key", "file", str(tmp_path)
            )

            assert os.path.exists(output_path)
            with open(output_path, "rb") as f:
                assert f.read() == b"binary_data"


class TestGetGroupShareLink:
    def test_get_group_share_link_success(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.share_link = "https://applink.feishu.cn/client/chat/oc_test"
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_link"

        with patch.object(
            mock_client.client.im.v1.chat, "link", return_value=mock_response
        ) as mock_link:
            link = mock_client.get_group_share_link("oc_test_chat")

            assert link == "https://applink.feishu.cn/client/chat/oc_test"
            mock_link.assert_called_once()

    def test_get_group_share_link_no_data(self, mock_client: LarkIMClient) -> None:
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.share_link = None
        mock_response.code = 0
        mock_response.get_log_id.return_value = "log_link"

        with patch.object(
            mock_client.client.im.v1.chat, "link", return_value=mock_response
        ):
            with pytest.raises(RuntimeError, match="no share_link"):
                mock_client.get_group_share_link("oc_test_chat")


class TestGetGroupInfo:
    def test_get_group_info_success(self, mock_client: LarkIMClient) -> None:
        mock_chat = MagicMock()
        mock_chat.chat_id = "oc_test_chat"
        mock_chat.name = "测试群聊"
        mock_chat.type = "group"

        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data = mock_chat
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_chat"

        with patch.object(
            mock_client.client.im.v1.chat, "get", return_value=mock_response
        ) as mock_chat_get:
            chat = mock_client.get_group_info("oc_test_chat")

            assert chat.chat_id == "oc_test_chat"
            assert chat.name == "测试群聊"
            mock_chat_get.assert_called_once()

    def test_list_groups_success(self, mock_client: LarkIMClient) -> None:
        mock_chat = MagicMock()
        mock_chat.chat_id = "oc_list_chat"

        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data.items = [mock_chat]
        mock_response.data.has_more = False
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_list"

        with patch.object(
            mock_client.client.im.v1.chat, "list", return_value=mock_response
        ) as mock_list:
            response = mock_client.list_groups()

            assert response.success()
            assert response.data.items is not None
            assert len(response.data.items) == 1
            mock_list.assert_called_once()


class TestGetGroupAnnouncement:
    def test_get_group_announcement_success(self, mock_client: LarkIMClient) -> None:
        mock_announcement = MagicMock()
        mock_announcement.content = "这是群公告内容"
        mock_announcement.revision = "1"
        mock_announcement.create_time = "1710000000"

        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.data = mock_announcement
        mock_response.code = 0
        mock_response.msg = "success"
        mock_response.get_log_id.return_value = "log_ann"

        with patch.object(
            mock_client.client.im.v1.chat_announcement, "get", return_value=mock_response
        ) as mock_ann_get:
            announcement = mock_client.get_group_announcement("oc_test_chat")

            assert announcement.content == "这是群公告内容"
            mock_ann_get.assert_called_once()


class TestCreateClientFromEnv:
    def test_create_client_from_env_success(self) -> None:
        with patch.dict(os.environ, {
            "LARK_APP_ID": "cli_test_app",
            "LARK_APP_SECRET": "test_secret_value",
        }, clear=False):
            client = create_client_from_env()
            assert client is not None
            assert isinstance(client, LarkIMClient)

    def test_create_client_from_env_missing_credentials(self) -> None:
        with patch.dict(os.environ, {
            "LARK_APP_ID": "",
            "LARK_APP_SECRET": "",
        }, clear=False):
            with pytest.raises(RuntimeError, match="must be set"):
                create_client_from_env()


class TestSendMessageResult:
    def test_send_message_result_creation(self) -> None:
        result = SendMessageResult(
            message_id="om_test",
            root_id="om_root",
            parent_id="om_parent",
            msg_type="text",
            create_time="1710000000",
            chat_id="oc_test",
            content="hello",
            sender={"id": "ou_user"},
            body={"content": "hello"},
        )

        assert result.message_id == "om_test"
        assert result.root_id == "om_root"
        assert result.msg_type == "text"


class TestEventHandling:
    def test_set_event_handler(self, mock_client: LarkIMClient) -> None:
        handler: MessageEventHandler = lambda event: None
        mock_client.set_event_handler(handler)

        assert mock_client._event_handler is not None

    def test_start_ws_without_handler(self, mock_client: LarkIMClient) -> None:
        with pytest.raises(RuntimeError, match="event_handler must be set"):
            mock_client.start_ws_listener()


class TestParseMessageResponse:
    def test_parse_response_none(self) -> None:
        with pytest.raises(RuntimeError, match="response data is None"):
            LarkIMClient._parse_message_response(None)

    def test_parse_response_missing_id(self) -> None:
        data = MagicMock()
        data.message_id = None
        with pytest.raises(RuntimeError, match="missing message_id"):
            LarkIMClient._parse_message_response(data)


# ==================== Lark API 集成测试（调用真实 API） ====================

skip_if_no_env = pytest.mark.skipif(
    not os.environ.get("LARK_APP_ID") or not os.environ.get("LARK_APP_SECRET"),
    reason="LARK_APP_ID and LARK_APP_SECRET must be set in .env",
)

skip_if_no_group = pytest.mark.skipif(
    not os.environ.get("GROUP_CHAT_IDS"),
    reason="GROUP_CHAT_IDS must be set in .env",
)


@pytest.mark.integration
class TestLarkIMIntegration:
    """集成测试：使用 .env 中的真实凭据调用 Lark API 进行群聊消息管理。

    这些测试会真实发送消息到群聊，并按需撤回清理。
    运行前请确保 .env 中的 LARK_APP_ID / LARK_APP_SECRET / GROUP_CHAT_IDS 正确配置，
    并且应用机器人已被添加到对应群聊中。
    """

    _sent_message_ids: List[str] = []

    @pytest.fixture(scope="class")
    def real_client(self) -> LarkIMClient:
        return create_client_from_env()

    @pytest.fixture(scope="class")
    def group_chat_id(self) -> str:
        raw = os.environ.get("GROUP_CHAT_IDS", "")
        return raw.split(",")[0].strip()

    def _recall_sent(self, client: LarkIMClient) -> None:
        for mid in reversed(self._sent_message_ids):
            try:
                client.recall_message(mid)
            except Exception:
                pass
        self._sent_message_ids.clear()

    # ==================== 发送消息 ====================

    @skip_if_no_env
    @skip_if_no_group
    def test_send_text_to_group(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """向群聊发送文本消息"""
        result = real_client.send_text_message(
            group_chat_id, "【测试消息】Lark API 集成测试 - 发送文本消息", receive_id_type="chat_id",
        )
        assert result.message_id is not None
        assert result.msg_type == "text"
        assert result.chat_id == group_chat_id
        self._sent_message_ids.append(result.message_id)

    @skip_if_no_env
    @skip_if_no_group
    def test_send_post_to_group(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """向群聊发送富文本消息"""
        post_content = {
            "zh_cn": {
                "title": "测试富文本",
                "content": [
                    [{"tag": "text", "text": "这是 Lark API 集成测试的富文本消息"}],
                ],
            }
        }
        result = real_client.send_message(
            group_chat_id, MessageContent.post(post_content), receive_id_type="chat_id",
        )
        assert result.message_id is not None
        assert result.msg_type == "post"
        self._sent_message_ids.append(result.message_id)

    @skip_if_no_env
    @skip_if_no_group
    def test_send_share_chat_to_group(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """向群聊发送群名片"""
        result = real_client.send_message(
            group_chat_id, MessageContent.share_chat(group_chat_id), receive_id_type="chat_id",
        )
        assert result.message_id is not None
        assert result.msg_type == "share_chat"
        self._sent_message_ids.append(result.message_id)

    # ==================== 获取群信息 ====================

    @skip_if_no_env
    @skip_if_no_group
    def test_get_group_info(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """获取群聊信息（API 实际返回 GetChatResponseBody，不包含 chat_id 字段）"""
        chat = real_client.get_group_info(group_chat_id)
        assert chat.name is not None

    @skip_if_no_env
    @skip_if_no_group
    def test_get_group_share_link(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """获取群分享链接"""
        link = real_client.get_group_share_link(group_chat_id, validity_period="week")
        assert link.startswith("https://")

    @skip_if_no_env
    def test_list_groups(self, real_client: LarkIMClient) -> None:
        """获取机器人可见的群列表"""
        response = real_client.list_groups(page_size=10)
        assert response.success()
        assert response.data is not None
        assert response.data.items is not None

    # ==================== 获取群公告 ====================

    @pytest.mark.xfail(reason="应用缺少 im:chat 权限", strict=False)
    @skip_if_no_env
    @skip_if_no_group
    def test_get_group_announcement(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """获取群公告（需要 im:chat 权限）"""
        announcement = real_client.get_group_announcement(group_chat_id)
        assert announcement.content is not None

    # ==================== 消息历史 ====================

    @skip_if_no_env
    @skip_if_no_group
    def test_get_conversation_history(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """获取群聊消息历史"""
        response = real_client.get_conversation_history(
            container_id=group_chat_id, page_size=5,
        )
        assert response.success()
        assert response.data is not None
        assert response.data.items is not None

    @skip_if_no_env
    @skip_if_no_group
    def test_get_all_conversation_history(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """分页获取全部群聊消息"""
        messages = real_client.get_all_conversation_history(
            container_id=group_chat_id, page_size=5,
        )
        assert len(messages) > 0

    # ==================== 消息交互全流程 ====================

    @skip_if_no_env
    @skip_if_no_group
    def test_reply_and_forward_and_edit(self, real_client: LarkIMClient, group_chat_id: str) -> None:
        """按顺序测试完整消息管理流程：发送 → 回复 → 获取详情 → 转发 → 编辑卡片消息"""
        # 1. 发送一条文本消息作为回复/转发的目标
        original = real_client.send_text_message(
            group_chat_id, "【测试消息】Lark API 集成测试 - 原始消息", receive_id_type="chat_id",
        )
        assert original.message_id is not None
        self._sent_message_ids.append(original.message_id)
        orig_msg_id = original.message_id

        # 2. 回复该消息
        reply = real_client.reply_message(orig_msg_id, MessageContent.text("【测试消息】Lark API 集成测试 - 回复消息"))
        assert reply.message_id is not None
        assert reply.msg_type == "text"
        self._sent_message_ids.append(reply.message_id)

        # 3. 获取回复的消息详情
        msg = real_client.get_message(reply.message_id)
        assert msg.message_id == reply.message_id
        assert msg.msg_type == "text"

        # 4. 转发原始消息到同一个群
        fwd = real_client.forward_message(orig_msg_id, group_chat_id, receive_id_type="chat_id")
        assert fwd.message_id is not None
        self._sent_message_ids.append(fwd.message_id)

        # 5. 先发一条卡片消息再编辑（仅卡片消息支持编辑）
        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "测试卡片"},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "原始卡片内容"}},
            ],
        }
        card_msg = real_client.send_message(
            group_chat_id, MessageContent.card(card_content), receive_id_type="chat_id",
        )
        assert card_msg.message_id is not None
        self._sent_message_ids.append(card_msg.message_id)

        edited_card = real_client.edit_message(
            card_msg.message_id,
            MessageContent.card({
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "已编辑卡片"},
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "编辑后的卡片内容"}},
                ],
            }),
        )
        assert edited_card.message_id == card_msg.message_id

    # ==================== 撤回消息 ====================

    @skip_if_no_env
    @skip_if_no_group
    def test_recall_all_sent_messages(self, real_client: LarkIMClient) -> None:
        """清理本轮测试发送的所有消息"""
        self._recall_sent(real_client)
        assert len(self._sent_message_ids) == 0