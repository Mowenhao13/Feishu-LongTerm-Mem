## 1. 模型注册器封装

在src/model/model.py 创建全局模型注册器 ModelProvider

ModelRegister分为LLMProvider, EmbeddingProvider, RerankerProvider



参考ref/lark-adapter里的lark_doc.go 新建doc提取器 使用飞书api进行轮询 加入防抖机制 将轮询频率与防抖机制参数写入.env文件 并加载 在prompts里加入专门针对文档决策管理的prompt 决策管理与lark_im一致 但决策去重，冲突判断，更新逻辑要针对文档结构进行调整（在test里测试） 当前可以先不用飞书api实现 在注释里加入TODO（作为未来拓展）当前阶段先使用读取本地文件的形式来做模拟 每当文档发生变化都进行决策提取 针对多文档和单文档

当前更新了飞书cli的配置 目前先测试im群聊消息的效果 需要调整决策卡片的推送时机 可以给决策卡片推送时机增加几个选项：固定频率（每周一次/每天一次/每天三次，次数可以让用户制定），决策一更新就推送 当前embedding和reranker暂时不可用 先不进行演示 需要创建脚本 清空并重新初始化记忆存储文件（根据用户指定路径进行操作 路径位于.env环境变量STORAGE_PATH里） 然后先将

将eval_data里的数据添加单人版（要融入决策冲突 重复决策 决策更新）  当前LARK_APP_ID和LARK_APP_SECRET都已经更新可用 用于在飞书演示项目决策提取 数据发送者名字改为UserOnly 只有一个发送者 消息条数可改为300～500条 调用飞书服务端api进行发送 可以先进行一两条消息的测试 测试响应成功后再开始发送全量消息 发送消息之前开启im检测器（长连接模式） 检测群聊消息 调用记忆系统进行决策提取与记忆构建 采用超图进行存储 调用已经就绪的reranker embedding模型进行索引构建 

kill掉所有main.py进程 修改send_demo_message.py 重命名为send_message.py 批次间隔要大于im检测器突发间隔 删除发送测试消息 直接全量发送 然后创建send_demo_message.py 调用服务端api 只发送两条消息到飞书群聊 带有决策性的消息  然后启动main.py 间隔2s后启动send_demo_messgae.py 观察main.py的日志输出

转发端口命令：

ssh -L 8000:localhost:8000 -L 8001:localhost:8001 ubuntu

# 实际 embedding 和 reranker 端口为 9000 和 9001
ssh -L 9000:localhost:9000 -L 9001:localhost:9001 ubuntu

现在我要生成整个项目的wiki 用作技术报告书 当前我已经生成了一个md文件再docs/wiki目录下 仔细翻阅整个项目 帮我补全wiki目录下已经创建的md文件 每个md文件里已经有写好的子标题 但需要你把内容和子标题改成中文 文件名称不变 注意：1. 可以根据实际项目情况 对md文件内容进行补充 md内容里不需要完整的项目代码 如有必要 用代码块展示出部分即可 参考deepwiki风格 2. 要在我指明生成流程图的地方生成可被成功渲染的流程图/其他形式的图 需要符合mermaid语法（语法不要太新 不然不兼容 写完后可以用工具check下） 3. 不用给代码文件创建引用 文档里出现的引用部分只有不同文档间片段的引用/导航

解释下修复1_dict_to_node sid 崩溃修复 然后保留当前决策 完成以下任务：1. 先将本次使用的群聊对话的消息使用scripts/send_message.py发送到飞书群聊 2. 先将ppt/images里的图片放入html里 然后可以适当扩充html到18页 多出来的那几页可以不用包含图片 将html里的技术栈那一页的部署里的claude desktop删除 只保留openclaw 然后暂时删除评估测试里的ExtractionEvaluator QA 评估 因为之前项目做过架构变更 测试为更新 所以暂时删除（技术栈评估里的12 场景 QA 数据集也要删除）最后Q&A部分将邮箱和github仓库地址换成下面的：mowenhao21@outlook.com, github.com/Mowenhao13/Feishu-LongTerm-Mem 与此同时 刚刚项目的部分代码发生调整 index.html里的内容也要同步修改 例如决策呈现树状结构 这个要预留一个图片的位置 我还没截图  3. 继续使用eval模式测试eval_data下的test_data.txt 并统计最终的llm调用量 并将llm调用量更新到docs/ppt/index.html 里 然后该测试里要体现决策之间的层级关系 