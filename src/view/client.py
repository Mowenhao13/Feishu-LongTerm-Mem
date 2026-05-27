import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableCreateHeader,
    AppTableField,
    AppTableRecord,
    BatchDeleteAppTableRecordRequest,
    BatchDeleteAppTableRecordRequestBody,
    CreateAppRequest,
    CreateAppResponse,
    CreateAppTableFieldRequest,
    CreateAppTableRecordRequest,
    CreateAppTableRecordResponse,
    CreateAppTableRequest,
    CreateAppTableRequestBody,
    ListAppTableFieldRequest,
    ReqApp,
    ReqTable,
    SearchAppTableRecordRequest,
    SearchAppTableRecordRequestBody,
    UpdateAppTableRecordRequest,
    UpdateAppTableRecordResponse,
)

from src.utils.logger import get_logger
from .schema import (
    ALL_FIELD_NAMES,
    FIELD_DECISION_ID,
    FIELD_PARENT,
    STATUS_OPTIONS,
    TABLE_NAME,
)

logger = get_logger(__name__)

META_FILE = Path(__file__).resolve().parent / ".view_meta.json"


class BaseViewClient:

    def __init__(self):
        self._client: Optional[lark.Client] = None
        self._base_token: Optional[str] = None
        self._table_id: Optional[str] = None
        self._user_token: Optional[str] = None
        self._load_meta()
        self._user_token = os.environ.get("LARK_USER_ACCESS_TOKEN", "").strip() or None

    def _get_client(self) -> lark.Client:
        if self._client is None:
            builder = lark.Client.builder().log_level(lark.LogLevel.ERROR)
            if self._user_token:
                builder.enable_set_token(True)
            else:
                builder.app_id(os.environ.get("LARK_APP_ID", "")) \
                    .app_secret(os.environ.get("LARK_APP_SECRET", ""))
            self._client = builder.build()
        return self._client

    def _get_request_option(self):
        if self._user_token:
            return lark.RequestOption.builder() \
                .user_access_token(self._user_token) \
                .build()
        return None

    def _meta_path(self) -> Path:
        return META_FILE

    def _load_meta(self) -> None:
        meta_path = self._meta_path()
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                self._base_token = data.get("base_token")
                self._table_id = data.get("table_id")
            except Exception:
                pass

    def _save_meta(self) -> None:
        data = {
            "base_token": self._base_token,
            "table_id": self._table_id,
        }
        self._meta_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ensure_base(self, name: str = "feishu-mem-决策看板") -> str:
        if self._base_token:
            return self._base_token

        client = self._get_client()
        body = ReqApp.builder().name(name).build()
        request = CreateAppRequest.builder().request_body(body).build()
        response: CreateAppResponse = client.bitable.v1.app.create(
            request, self._get_request_option()
        )

        if not response.success():
            raise RuntimeError(
                f"Failed to create Base: code={response.code}, msg={response.msg}"
            )

        self._base_token = response.data.app.app_token
        self._save_meta()
        logger.info("Created Base: %s (token=%s)", name, self._base_token)
        return self._base_token

    def ensure_table(self) -> str:
        if self._table_id:
            self._ensure_fields_exist()
            return self._table_id

        base_token = self.ensure_base()
        client = self._get_client()

        fields = [
            AppTableCreateHeader.builder()
                .field_name(FIELD_DECISION_ID).type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策主题").type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策版本").type(2).build(),
            AppTableCreateHeader.builder()
                .field_name("决策状态").type(3)
                .property(self._build_single_select_property(STATUS_OPTIONS)).build(),
            AppTableCreateHeader.builder()
                .field_name("决策标题").type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策内容").type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策关联人").type(11).build(),
            AppTableCreateHeader.builder()
                .field_name("决策提出时间").type(5).build(),
            AppTableCreateHeader.builder()
                .field_name("决策热点值").type(2).build(),
            AppTableCreateHeader.builder()
                .field_name("冲突关联决策").type(1).build(),
            AppTableCreateHeader.builder()
                .field_name(FIELD_PARENT).type(1).build(),
        ]

        body = ReqTable.builder() \
            .name(TABLE_NAME) \
            .default_view_name("决策视图") \
            .fields(fields) \
            .build()

        request = CreateAppTableRequest.builder() \
            .app_token(base_token) \
            .request_body(CreateAppTableRequestBody.builder().table(body).build()) \
            .build()

        response = client.bitable.v1.app_table.create(
            request, self._get_request_option()
        )

        if not response.success():
            raise RuntimeError(
                f"Failed to create table: code={response.code}, msg={response.msg}"
            )

        self._table_id = response.data.table_id
        self._save_meta()
        logger.info("Created table: %s (id=%s)", TABLE_NAME, self._table_id)
        return self._table_id

    def _ensure_fields_exist(self) -> None:
        if not self._base_token or not self._table_id:
            return
        client = self._get_client()
        option = self._get_request_option()

        list_req = ListAppTableFieldRequest.builder() \
            .app_token(self._base_token).table_id(self._table_id) \
            .build()
        list_resp = client.bitable.v1.app_table_field.list(list_req, option)
        if not list_resp.success():
            logger.warning("Failed to list fields: code=%s, msg=%s", list_resp.code, list_resp.msg)
            return

        existing_names: set = set()
        if list_resp.data and list_resp.data.items:
            existing_names = {item.field_name for item in list_resp.data.items}

        for field_name in ALL_FIELD_NAMES:
            if field_name in existing_names:
                continue

            if field_name == "决策状态":
                new_field = AppTableField.builder() \
                    .field_name(field_name).type(3) \
                    .property(self._build_single_select_property(STATUS_OPTIONS)) \
                    .build()
            elif field_name == "决策关联人":
                new_field = AppTableField.builder() \
                    .field_name(field_name).type(11) \
                    .build()
            elif field_name == "决策提出时间":
                new_field = AppTableField.builder() \
                    .field_name(field_name).type(5) \
                    .build()
            elif field_name == "决策热点值":
                new_field = AppTableField.builder() \
                    .field_name(field_name).type(2) \
                    .build()
            elif field_name == "决策版本":
                new_field = AppTableField.builder() \
                    .field_name(field_name).type(2) \
                    .build()
            else:
                new_field = AppTableField.builder() \
                    .field_name(field_name).type(1) \
                    .build()

            create_req = CreateAppTableFieldRequest.builder() \
                .app_token(self._base_token).table_id(self._table_id) \
                .request_body(new_field) \
                .build()
            create_resp = client.bitable.v1.app_table_field.create(create_req, self._get_request_option())
            if create_resp.success():
                logger.info("Created missing field: %s", field_name)
            else:
                logger.warning("Failed to create field %s: code=%s, msg=%s",
                               field_name, create_resp.code, create_resp.msg)

    @staticmethod
    def _build_single_select_property(options: List[Dict[str, Any]]) -> Any:
        from lark_oapi.api.bitable.v1 import (
            AppTableFieldProperty,
            AppTableFieldPropertyOption,
        )
        opts = [AppTableFieldPropertyOption.builder()
                .name(o["name"]).color(o.get("color", 0)).build()
                for o in options]
        return AppTableFieldProperty.builder().options(opts).build()

    def search_record(self, sid: str) -> Optional[str]:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()

        request = SearchAppTableRecordRequest.builder() \
            .app_token(base_token).table_id(table_id) \
            .request_body(SearchAppTableRecordRequestBody.builder()
                .field_names([FIELD_DECISION_ID])
                .filter(self._build_filter(FIELD_DECISION_ID, sid))
                .build()) \
            .build()

        response = client.bitable.v1.app_table_record.search(
            request, self._get_request_option()
        )

        if response.success() and response.data and response.data.items:
            return response.data.items[0].record_id
        return None

    @staticmethod
    def _build_filter(field_name: str, value: str) -> Any:
        from lark_oapi.api.bitable.v1 import Condition, FilterInfo
        return FilterInfo.builder().conjunction("and").conditions([
            Condition.builder().field_name(field_name).operator("is").value([value]).build()
        ]).build()

    def upsert_record(self, fields: Dict[str, Any]) -> None:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()

        sid = fields.get(FIELD_DECISION_ID, "")
        existing = self.search_record(sid) if sid else None
        option = self._get_request_option()

        if existing:
            request = UpdateAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .record_id(existing) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()
            response = client.bitable.v1.app_table_record.update(request, option)
        else:
            request = CreateAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()
            response = client.bitable.v1.app_table_record.create(request, option)

        if not response.success():
            logger.error(
                "Failed to upsert record for %s: code=%s, msg=%s",
                sid, response.code, response.msg,
            )

    def delete_all_records(self) -> None:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()
        option = self._get_request_option()

        page_token: Optional[str] = None
        all_record_ids: List[str] = []

        while True:
            req_builder = SearchAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id)
            if page_token:
                req_builder.page_token(page_token)

            request = req_builder.request_body(
                SearchAppTableRecordRequestBody.builder()
                    .field_names([FIELD_DECISION_ID]).build()
            ).build()

            response = client.bitable.v1.app_table_record.search(request, option)
            if not response.success():
                logger.warning("Failed to search records for deletion: code=%s", response.code)
                return

            if response.data and response.data.items:
                all_record_ids.extend(item.record_id for item in response.data.items)

            if response.data and getattr(response.data, "has_more", False):
                page_token = getattr(response.data, "page_token", None)
            else:
                break

        if not all_record_ids:
            return

        for i in range(0, len(all_record_ids), 200):
            batch = all_record_ids[i:i + 200]
            batch_req = BatchDeleteAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .request_body(BatchDeleteAppTableRecordRequestBody.builder()
                    .records(batch).build()) \
                .build()
            client.bitable.v1.app_table_record.batch_delete(batch_req, option)
            time.sleep(0.5)

        logger.info("Deleted %d records from Base", len(all_record_ids))

    def batch_create_records(self, records: List[Dict[str, Any]]) -> None:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()
        option = self._get_request_option()

        for i, record in enumerate(records):
            request = CreateAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .request_body(AppTableRecord.builder().fields(record).build()) \
                .build()
            response = client.bitable.v1.app_table_record.create(request, option)
            if not response.success():
                logger.error(
                    "Failed to create record %d (%s): code=%s, msg=%s",
                    i, record.get(FIELD_DECISION_ID, ""), response.code, response.msg,
                )
            if (i + 1) % 10 == 0:
                time.sleep(0.5)