# 决策可视化多维表格方案

## 环境变量
`user_access_token`: u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB

## 服务端api示例
### 1. 创建多维表格
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: CreateAppRequest = CreateAppRequest.builder() \
        .request_body(ReqApp.builder()
            .name("一篇新的多维表格")
            .folder_token("fldcnqquW1svRIYVT2Np6Iabcef")
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: CreateAppResponse = client.bitable.v1.app.create(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 2. 获取多维表格
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: GetAppRequest = GetAppRequest.builder() \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: GetAppResponse = client.bitable.v1.app.get(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app.get failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 3. 新增一个数据表
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: CreateAppTableRequest = CreateAppTableRequest.builder() \
        .request_body(CreateAppTableRequestBody.builder()
            .table(ReqTable.builder()
                .name("数据表名称")
                .default_view_name("默认的表格视图")
                .fields([AppTableCreateHeader.builder()
                    .field_name("索引字段")
                    .type(1)
                    .build(), 
                    AppTableCreateHeader.builder()
                    .field_name("单选")
                    .type(3)
                    .ui_type("SingleSelect")
                    .property(AppTableFieldProperty.builder()
                        .options([AppTableFieldPropertyOption.builder()
                            .name("Enabled")
                            .color(0)
                            .build(), 
                            AppTableFieldPropertyOption.builder()
                            .name("Disabled")
                            .color(1)
                            .build(), 
                            AppTableFieldPropertyOption.builder()
                            .name("Draft")
                            .color(2)
                            .build()
                            ])
                        .build())
                    .build()
                    ])
                .build())
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: CreateAppTableResponse = client.bitable.v1.app_table.create(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 4. 新增多个数据表
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: CreateAppTableRequest = CreateAppTableRequest.builder() \
        .request_body(CreateAppTableRequestBody.builder()
            .table(ReqTable.builder()
                .name("数据表名称")
                .default_view_name("默认的表格视图")
                .fields([AppTableCreateHeader.builder()
                    .field_name("索引字段")
                    .type(1)
                    .build(), 
                    AppTableCreateHeader.builder()
                    .field_name("单选")
                    .type(3)
                    .ui_type("SingleSelect")
                    .property(AppTableFieldProperty.builder()
                        .options([AppTableFieldPropertyOption.builder()
                            .name("Enabled")
                            .color(0)
                            .build(), 
                            AppTableFieldPropertyOption.builder()
                            .name("Disabled")
                            .color(1)
                            .build(), 
                            AppTableFieldPropertyOption.builder()
                            .name("Draft")
                            .color(2)
                            .build()
                            ])
                        .build())
                    .build()
                    ])
                .build())
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: CreateAppTableResponse = client.bitable.v1.app_table.create(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 5. 更新数据表
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: PatchAppTableRequest = PatchAppTableRequest.builder() \
        .request_body(PatchAppTableRequestBody.builder()
            .name("新的数据表名称")
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: PatchAppTableResponse = client.bitable.v1.app_table.patch(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table.patch failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 6. 新增记录
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: CreateAppTableRecordRequest = CreateAppTableRecordRequest.builder() \
        .request_body(AppTableRecord.builder()
            .fields({"人员":[{"id":"ou_2910013f1e6456f16a0ce75ede9abcef"},{"id":"ou_e04138c9633dd0d2ea166d79f54abcef"}],"任务名称":"拜访潜在客户","单向关联":["recHTLvO7x","recbS8zb2m"],"单选":"选项1","双向关联":["recHTLvO7x","recbS8zb2m"],"地理位置":"116.397755,39.903179","复选框":true,"多选":["选项1","选项2"],"工时":10,"日期":1674206443000,"条码":"+$$3170930509104X512356","电话号码":"1302616xxxx","群组":[{"id":"oc_cd07f55f14d6f4a4f1b51504e7e97f48"}],"评分":3,"货币":3,"超链接":{"link":"https://www.feishu.cn/product/base","text":"飞书多维表格官网"},"进度":0.25,"附件":[{"file_token":"DRiFbwaKsoZaLax4WKZbEGCccoe"},{"file_token":"BZk3bL1Enoy4pzxaPL9bNeKqcLe"},{"file_token":"EmL4bhjFFovrt9xZgaSbjJk9c1b"},{"file_token":"Vl3FbVkvnowlgpxpqsAbBrtFcrd"}]})
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: CreateAppTableRecordResponse = client.bitable.v1.app_table_record.create(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 7. 更新记录
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: UpdateAppTableRecordRequest = UpdateAppTableRecordRequest.builder() \
        .request_body(AppTableRecord.builder()
            .fields({"人员":[{"id":"ou_2910013f1e6456f16a0ce75ede950a0a"},{"id":"ou_e04138c9633dd0d2ea166d79f548ab5d"}],"单向关联":["recHTLvO7x","recbS8zb2m"],"单选":"选项3","双向关联":["recHTLvO7x","recbS8zb2m"],"地理位置":"116.397755,39.903179","复选框":true,"多选":["选项1","选项2"],"数字":100,"文本":"文本内容","日期":1674206443000,"条码":"qawqe","电话号码":"13026162666","索引":"索引列文本类型","群组":[{"id":"oc_cd07f55f14d6f4a4f1b51504e7e97f48"}],"评分":3,"货币":3,"超链接":{"link":"https://www.feishu.cn/product/base","text":"飞书多维表格官网"},"进度":0.25,"附件":[{"file_token":"Vl3FbVkvnowlgpxpqsAbBrtFcrd"}]})
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: UpdateAppTableRecordResponse = client.bitable.v1.app_table_record.update(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.update failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 8. 查询记录
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: SearchAppTableRecordRequest = SearchAppTableRecordRequest.builder() \
        .app_token("") \
        .table_id("") \
        .user_id_type("") \
        .page_token("") \
        .page_size() \
        .request_body(SearchAppTableRecordRequestBody.builder()
            .view_id("vewqhz51lk")
            .field_names(["字段1", "字段2"])
            .sort([Sort.builder()
                .field_name("多行文本")
                .desc(True)
                .build()
                ])
            .filter()
            .automatic_fields()
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: SearchAppTableRecordResponse = client.bitable.v1.app_table_record.search(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_record.search failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

### 9. 更新字段
```python
import json

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *


# SDK 使用说明: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/preparations-before-development
# 以下示例代码默认根据文档示例值填充，如果存在代码问题，请在 API 调试台填上相关必要参数后再复制代码使用
def main():
    # 创建client
    # 使用 user_access_token 需开启 token 配置, 并在 request_option 中配置 token
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 构造请求对象
    request: UpdateAppTableFieldRequest = UpdateAppTableFieldRequest.builder() \
        .request_body(AppTableField.builder()
            .field_name("人员")
            .type(11)
            .property(AppTableFieldProperty.builder()
                .multiple(True)
                .build())
            .build()) \
        .build()

    # 发起请求
    option = lark.RequestOption.builder().user_access_token("u-eHJHuqV7lb98j6l1ZQokDIlg7T1Ah0CrN0wGYRg020lB").build()
    response: UpdateAppTableFieldResponse = client.bitable.v1.app_table_field.update(request, option)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.bitable.v1.app_table_field.update failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


if __name__ == "__main__":
    main()
```

## 表格设计
### 字段设计
- 决策ID 
- 决策主题
- 决策版本
- 决策状态
- 决策标题
- 决策内容
- 决策关联人
- 决策提出时间
- 决策热点值
- 决策冲突关联决策ID（若无冲突 则不填）

## 表格实时更新逻辑
- 一旦存储决策的git仓库更新 就更新多维表格
- 多维表格只展示当前分支下最新的version字段对应的决策 若存在多个相同version 及冲突 需要在决策状态里标注红色 说明决策冲突
- 相同主题的决策优先放在一起 冲突决策优先放在一起
- 相关操作可参考scripts/mcp

当前整个项目有什么值得拓展的 在evaluation部分能否加大数据样本量进行测试 重点测试跨群聊 用eval模式 