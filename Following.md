## 1. 模型注册器封装

在src/model/model.py 创建全局模型注册器 ModelProvider

ModelRegister分为LLMProvider, EmbeddingProvider, RerankerProvider



参考ref/lark-adapter里的lark_doc.go 新建doc提取器 使用飞书api进行轮询 加入防抖机制 将轮询频率与防抖机制参数写入.env文件 并加载 在prompts里加入专门针对文档决策管理的prompt 决策管理与lark_im一致 但决策去重，冲突判断，更新逻辑要针对文档结构进行调整（在test里测试） 当前可以先不用飞书api实现 在注释里加入TODO（作为未来拓展）当前阶段先使用读取本地文件的形式来做模拟 每当文档发生变化都进行决策提取 针对多文档和单文档

当前更新了飞书cli的配置 目前先测试im群聊消息的效果 需要调整决策卡片的推送时机 可以给决策卡片推送时机增加几个选项：固定频率（每周一次/每天一次/每天三次，次数可以让用户制定），决策一更新就推送 当前embedding和reranker暂时不可用 先不进行演示 需要创建脚本 清空并重新初始化记忆存储文件（根据用户指定路径进行操作 路径位于.env环境变量STORAGE_PATH里） 然后先将

将eval_data里的数据添加单人版（要融入决策冲突 重复决策 决策更新）  当前LARK_APP_ID和LARK_APP_SECRET都已经更新可用 用于在飞书演示项目决策提取 数据发送者名字改为UserOnly 只有一个发送者 消息条数可改为300～500条 调用飞书服务端api进行发送 可以先进行一两条消息的测试 测试响应成功后再开始发送全量消息 发送消息之前开启im检测器（长连接模式） 检测群聊消息 调用记忆系统进行决策提取与记忆构建 采用超图进行存储 调用已经就绪的reranker embedding模型进行索引构建 

kill掉所有main.py进程 修改send_demo_message.py 重命名为send_message.py 批次间隔要大于im检测器突发间隔 删除发送测试消息 直接全量发送 然后创建send_demo_message.py 调用服务端api 只发送两条消息到飞书群聊 带有决策性的消息  然后启动main.py 间隔2s后启动send_demo_messgae.py 观察main.py的日志输出

转发端口命令：

ssh -L 8000:localhost:8000 -L 8001:localhost:8001 ubuntu

