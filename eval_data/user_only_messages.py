"""
单人演示数据 — UserOnly 的 400 条群聊消息

场景设计：
  1. 技术架构决策     (~100条)  微服务↔单体, 冲突+更新+重复
  2. 前端技术选型     (~80条)   React↔Vue.js, 冲突+更新+重复
  3. 项目排期         (~80条)   上线时间变更, 更新+冲突
  4. 代码规范         (~50条)   ESLint→Biome, 更新+重复
  5. 测试策略         (~50条)   覆盖率标准, 冲突+更新
  6. 填充消息         (~40条)   非决策消息, 问候/闲聊
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

BATCH_SIZE = 20          # 每批发送条数
BATCH_INTERVAL = 10      # 批次间隔（秒）— 大于 IM 检测器突发间隔 5s
MSG_INTERVAL = 0.3       # 同批次内消息间隔（秒）


@dataclass
class ScenarioMessage:
    """单条消息"""
    text: str
    scenario: str = ""          # 所属场景标签
    decision_type: str = ""     # create | update | conflict | duplicate | none


def build_messages() -> List[ScenarioMessage]:
    msgs: List[ScenarioMessage] = []

    # ==================== 场景 1: 技术架构决策 (~100条) ====================

    msgs.append(ScenarioMessage("大家好，我是UserOnly，今天开始讨论项目的一些决策", "arch_intro", "none"))
    msgs.append(ScenarioMessage("首先说一下整体架构，我觉得微服务架构比较适合我们的场景", "arch_1", "none"))
    msgs.append(ScenarioMessage("微服务的好处是独立部署、独立扩展，团队可以并行开发", "arch_1", "none"))
    msgs.append(ScenarioMessage("而且微服务之间通过API通信，技术栈可以灵活选择", "arch_1", "none"))
    msgs.append(ScenarioMessage("我决定采用微服务架构来构建我们的后端系统", "arch_1", "create"))

    msgs.append(ScenarioMessage("每个微服务使用独立的数据库，避免耦合", "arch_2", "none"))
    msgs.append(ScenarioMessage("服务之间通过gRPC进行通信", "arch_2", "none"))
    msgs.append(ScenarioMessage("API网关使用Kong作为入口统一管理", "arch_2", "none"))
    msgs.append(ScenarioMessage("服务注册与发现用Consul来实现", "arch_2", "none"))
    msgs.append(ScenarioMessage("服务之间通信统一用gRPC协议", "arch_2", "create"))

    msgs.append(ScenarioMessage("不过最近想了想，微服务架构的运维成本确实比较高", "arch_conflict", "none"))
    msgs.append(ScenarioMessage("我们现在团队规模不大，微服务的维护成本可能承担不了", "arch_conflict", "none"))
    msgs.append(ScenarioMessage("单体架构在初期开发效率更高，部署也更简单", "arch_conflict", "none"))
    msgs.append(ScenarioMessage("我决定改用单体架构，先快速迭代起来", "arch_conflict", "conflict"))

    msgs.append(ScenarioMessage("但单体架构以后拆分也会很麻烦", "arch_revert", "none"))
    msgs.append(ScenarioMessage("而且微服务架构的技术选型已经做了不少工作", "arch_revert", "none"))
    msgs.append(ScenarioMessage("综合考虑，还是决定回到微服务架构", "arch_revert", "update"))

    msgs.append(ScenarioMessage("不过微服务的粒度需要仔细划分", "arch_refine", "none"))
    msgs.append(ScenarioMessage("我决定采用微服务+单体混合架构", "arch_refine", "none"))
    msgs.append(ScenarioMessage("核心业务用微服务，边缘模块先用单体", "arch_refine", "none"))
    msgs.append(ScenarioMessage("等业务规模起来后再逐步拆分单体部分", "arch_refine", "none"))
    msgs.append(ScenarioMessage("就这么定了，混合架构方案", "arch_refine", "update"))

    msgs.append(ScenarioMessage("今天天气真不错", "filler_1", "none"))
    msgs.append(ScenarioMessage("继续讨论架构方案", "arch_continue", "none"))
    msgs.append(ScenarioMessage("服务拆分按照业务域来划分", "arch_3", "none"))
    msgs.append(ScenarioMessage("用户服务、订单服务、支付服务各自独立", "arch_3", "none"))
    msgs.append(ScenarioMessage("每个服务都有自己的CI/CD流水线", "arch_3", "none"))
    msgs.append(ScenarioMessage("服务按业务域拆分的方案确定下来", "arch_3", "create"))

    msgs.append(ScenarioMessage("容器化方案用Docker+Kubernetes", "arch_4", "none"))
    msgs.append(ScenarioMessage("K8s集群用阿里云ACK托管集群", "arch_4", "none"))
    msgs.append(ScenarioMessage("这样运维工作量大减", "arch_4", "none"))
    msgs.append(ScenarioMessage("容器化方案确定：Docker+K8s", "arch_4", "create"))

    msgs.append(ScenarioMessage("对了，再次确认一下混合架构的方案", "arch_dup", "none"))
    msgs.append(ScenarioMessage("核心业务用微服务，边缘用单体", "arch_dup", "none"))
    msgs.append(ScenarioMessage("这个方案我们之前定过了，保持不变", "arch_dup", "duplicate"))

    msgs.append(ScenarioMessage("日志收集用ELK栈", "arch_5", "none"))
    msgs.append(ScenarioMessage("Elasticsearch做存储，Logstash收集，Kibana可视化", "arch_5", "none"))
    msgs.append(ScenarioMessage("监控用Prometheus+Grafana", "arch_5", "none"))
    msgs.append(ScenarioMessage("日志和监控方案确定", "arch_5", "create"))
    msgs.append(ScenarioMessage("ELK+Prometheus+Grafana，就这么办", "arch_5", "duplicate"))

    msgs.append(ScenarioMessage("配置中心用Nacos", "arch_6", "none"))
    msgs.append(ScenarioMessage("Nacos支持配置管理和服务发现", "arch_6", "none"))
    msgs.append(ScenarioMessage("用Nacos做配置中心", "arch_6", "create"))
    msgs.append(ScenarioMessage("Nacos配置中心，确认一下，没问题", "arch_6", "duplicate"))

    # ==================== 场景 2: 前端技术选型 (~80条) ====================

    msgs.append(ScenarioMessage("前端技术选型也要讨论一下", "fe_1", "none"))
    msgs.append(ScenarioMessage("目前主流框架有React、Vue.js、Angular", "fe_1", "none"))
    msgs.append(ScenarioMessage("React的社区生态最丰富，组件库选择多", "fe_1", "none"))
    msgs.append(ScenarioMessage("而且React Native可以做移动端", "fe_1", "none"))
    msgs.append(ScenarioMessage("我决定前端使用React框架", "fe_1", "create"))

    msgs.append(ScenarioMessage("UI组件库用Ant Design", "fe_2", "none"))
    msgs.append(ScenarioMessage("Ant Design的组件比较完善，文档也很好", "fe_2", "none"))
    msgs.append(ScenarioMessage("UI组件库就用Ant Design了", "fe_2", "create"))

    msgs.append(ScenarioMessage("状态管理用Redux Toolkit", "fe_3", "none"))
    msgs.append(ScenarioMessage("Redux Toolkit是官方推荐的状态管理方案", "fe_3", "none"))
    msgs.append(ScenarioMessage("状态管理用Redux Toolkit", "fe_3", "create"))

    msgs.append(ScenarioMessage("不过想了想，Vue.js的学习曲线更平缓", "fe_conflict", "none"))
    msgs.append(ScenarioMessage("Vue3的组合式API开发体验也很好", "fe_conflict", "none"))
    msgs.append(ScenarioMessage("而且Vue在中国社区更活跃", "fe_conflict", "none"))
    msgs.append(ScenarioMessage("我决定改为使用Vue.js", "fe_conflict", "conflict"))

    msgs.append(ScenarioMessage("Vue的生态工具也够用", "fe_vue", "none"))
    msgs.append(ScenarioMessage("UI库用Element Plus", "fe_vue", "none"))
    msgs.append(ScenarioMessage("状态管理用Pinia", "fe_vue", "none"))
    msgs.append(ScenarioMessage("Element Plus+Pinia，Vue技术栈确定", "fe_vue", "create"))

    msgs.append(ScenarioMessage("但React的TypeScript支持更好", "fe_revert", "none"))
    msgs.append(ScenarioMessage("而且团队成员React经验更丰富", "fe_revert", "none"))
    msgs.append(ScenarioMessage("最后还是决定用React", "fe_revert", "update"))
    msgs.append(ScenarioMessage("React+TypeScript+Ant Design，就这么定了", "fe_revert", "update"))

    msgs.append(ScenarioMessage("构建工具用Vite", "fe_4", "none"))
    msgs.append(ScenarioMessage("Vite开发体验好，构建速度快", "fe_4", "none"))
    msgs.append(ScenarioMessage("构建工具用Vite", "fe_4", "create"))

    msgs.append(ScenarioMessage("再次确认，前端是React+TypeScript+Ant Design+Vite", "fe_dup", "duplicate"))
    msgs.append(ScenarioMessage("这个方案不变", "fe_dup", "none"))

    msgs.append(ScenarioMessage("微前端用Module Federation", "fe_5", "none"))
    msgs.append(ScenarioMessage("Module Federation可以实现子应用独立部署", "fe_5", "none"))
    msgs.append(ScenarioMessage("微前端方案用Module Federation", "fe_5", "create"))

    msgs.append(ScenarioMessage("测试框架用Vitest", "fe_6", "none"))
    msgs.append(ScenarioMessage("Vitest和Vite无缝集成", "fe_6", "none"))
    msgs.append(ScenarioMessage("前端测试用Vitest", "fe_6", "create"))
    msgs.append(ScenarioMessage("饿了吗，先点个外卖", "filler_2", "none"))
    msgs.append(ScenarioMessage("继续，前端打包分析用webpack-bundle-analyzer", "fe_7", "none"))
    msgs.append(ScenarioMessage("不过Vite自带了rollup-plugin-visualizer", "fe_7", "none"))
    msgs.append(ScenarioMessage("用rollup-plugin-visualizer做打包分析", "fe_7", "create"))

    # ==================== 场景 3: 项目排期 (~80条) ====================

    msgs.append(ScenarioMessage("项目排期需要确定一下", "schedule_1", "none"))
    msgs.append(ScenarioMessage("第一阶段开发预计需要3周", "schedule_1", "none"))
    msgs.append(ScenarioMessage("包括需求分析和核心功能开发", "schedule_1", "none"))
    msgs.append(ScenarioMessage("第一阶段3周完成", "schedule_1", "create"))

    msgs.append(ScenarioMessage("第二阶段是测试和优化", "schedule_2", "none"))
    msgs.append(ScenarioMessage("测试需要1周，性能优化需要1周", "schedule_2", "none"))
    msgs.append(ScenarioMessage("第二阶段2周完成", "schedule_2", "create"))

    msgs.append(ScenarioMessage("整体项目计划6月1日上线", "schedule_3", "none"))
    msgs.append(ScenarioMessage("包括：开发3周+测试1周+部署1周", "schedule_3", "none"))
    msgs.append(ScenarioMessage("6月1日正式上线", "schedule_3", "create"))

    msgs.append(ScenarioMessage("但是需求变更了，需要增加支付模块", "schedule_update", "none"))
    msgs.append(ScenarioMessage("支付模块开发需要额外2周", "schedule_update", "none"))
    msgs.append(ScenarioMessage("上线时间推迟到6月15日", "schedule_update", "update"))

    msgs.append(ScenarioMessage("QA反馈需要更多测试时间", "schedule_delay", "none"))
    msgs.append(ScenarioMessage("安全测试也需要加进来", "schedule_delay", "none"))
    msgs.append(ScenarioMessage("上线时间再推迟到7月1日", "schedule_delay", "update"))

    msgs.append(ScenarioMessage("周末加个班，争取6月20日上线", "schedule_conflict", "none"))
    msgs.append(ScenarioMessage("不能推迟太久了，业务方有压力", "schedule_conflict", "none"))
    msgs.append(ScenarioMessage("提前到6月20日上线", "schedule_conflict", "conflict"))

    msgs.append(ScenarioMessage("不过安全测试不能省", "schedule_final", "none"))
    msgs.append(ScenarioMessage("6月20日上线，但安全测试并行进行", "schedule_final", "none"))
    msgs.append(ScenarioMessage("最终决定6月20日上线，安全测试并行", "schedule_final", "update"))
    msgs.append(ScenarioMessage("6月20日上线，确认", "schedule_final", "duplicate"))

    msgs.append(ScenarioMessage("每两周一个迭代", "schedule_4", "none"))
    msgs.append(ScenarioMessage("迭代周期为两周", "schedule_4", "none"))
    msgs.append(ScenarioMessage("迭代周期定为两周", "schedule_4", "create"))

    msgs.append(ScenarioMessage("今天好累，喝杯咖啡", "filler_3", "none"))
    msgs.append(ScenarioMessage("每天早上10点站会", "schedule_5", "none"))
    msgs.append(ScenarioMessage("站会控制在15分钟内", "schedule_5", "none"))
    msgs.append(ScenarioMessage("早上10点站会，15分钟", "schedule_5", "create"))

    msgs.append(ScenarioMessage("每周五下午做代码评审", "schedule_6", "none"))
    msgs.append(ScenarioMessage("代码评审轮流主持", "schedule_6", "none"))
    msgs.append(ScenarioMessage("周五下午代码评审，轮流主持", "schedule_6", "create"))
    msgs.append(ScenarioMessage("想喝奶茶", "filler_4", "none"))

    # ==================== 场景 4: 代码规范 (~50条) ====================

    msgs.append(ScenarioMessage("代码规范也要统一一下", "code_1", "none"))
    msgs.append(ScenarioMessage("使用ESLint做代码检查", "code_1", "none"))
    msgs.append(ScenarioMessage("Prettier做代码格式化", "code_1", "none"))
    msgs.append(ScenarioMessage("ESLint+Prettier规范代码风格", "code_1", "create"))

    msgs.append(ScenarioMessage("TypeScript使用严格模式", "code_2", "none"))
    msgs.append(ScenarioMessage("strict: true", "code_2", "none"))
    msgs.append(ScenarioMessage("TypeScript严格模式", "code_2", "create"))

    msgs.append(ScenarioMessage("现在Biome工具更好用", "code_update", "none"))
    msgs.append(ScenarioMessage("Biome集成了lint和format，速度更快", "code_update", "none"))
    msgs.append(ScenarioMessage("决定改用Biome代替ESLint+Prettier", "code_update", "update"))

    msgs.append(ScenarioMessage("Biome配置：推荐配置+自定义规则", "code_3", "none"))
    msgs.append(ScenarioMessage("禁止使用any类型", "code_3", "none"))
    msgs.append(ScenarioMessage("Biome配置确定：推荐配置+禁止any", "code_3", "create"))

    msgs.append(ScenarioMessage("再次确认，代码规范统一用Biome", "code_dup", "duplicate"))
    msgs.append(ScenarioMessage("之前用过ESLint，现在都迁到Biome", "code_dup", "none"))

    msgs.append(ScenarioMessage("Git提交规范用Conventional Commits", "code_4", "none"))
    msgs.append(ScenarioMessage("feat/fix/chore/docs等前缀", "code_4", "none"))
    msgs.append(ScenarioMessage("Git提交采用Conventional Commits规范", "code_4", "create"))
    msgs.append(ScenarioMessage("commitlint校验提交信息", "code_5", "none"))
    msgs.append(ScenarioMessage("husky做git hooks", "code_5", "none"))
    msgs.append(ScenarioMessage("commitlint+husky自动化校验", "code_5", "create"))
    msgs.append(ScenarioMessage("今天工作告一段落", "filler_5", "none"))

    # ==================== 场景 5: 测试策略 (~50条) ====================

    msgs.append(ScenarioMessage("测试策略需要定下来", "test_1", "none"))
    msgs.append(ScenarioMessage("单元测试覆盖率目标80%", "test_1", "none"))
    msgs.append(ScenarioMessage("使用Jest做单元测试", "test_1", "none"))
    msgs.append(ScenarioMessage("单元测试覆盖率80%，用Jest", "test_1", "create"))

    msgs.append(ScenarioMessage("集成测试用Supertest", "test_2", "none"))
    msgs.append(ScenarioMessage("端到端测试用Cypress", "test_2", "none"))
    msgs.append(ScenarioMessage("集成测试Supertest，E2E用Cypress", "test_2", "create"))

    msgs.append(ScenarioMessage("覆盖率80%可能有点高", "test_update", "none"))
    msgs.append(ScenarioMessage("核心模块80%，普通模块60%", "test_update", "none"))
    msgs.append(ScenarioMessage("覆盖率标准调整为：核心80%，普通60%", "test_update", "update"))

    msgs.append(ScenarioMessage("想了想，覆盖率还是要严格要求", "test_conflict", "none"))
    msgs.append(ScenarioMessage("质量不能打折扣，全部模块必须80%以上", "test_conflict", "none"))
    msgs.append(ScenarioMessage("覆盖率标准改回全部模块80%", "test_conflict", "conflict"))

    msgs.append(ScenarioMessage("API测试用Postman+Newman", "test_3", "none"))
    msgs.append(ScenarioMessage("Postman做手动测试，Newman做自动化", "test_3", "none"))
    msgs.append(ScenarioMessage("API测试用Postman+Newman", "test_3", "create"))

    msgs.append(ScenarioMessage("压力测试用k6", "test_4", "none"))
    msgs.append(ScenarioMessage("k6脚本用JavaScript编写，很方便", "test_4", "none"))
    msgs.append(ScenarioMessage("压力测试工具用k6", "test_4", "create"))
    msgs.append(ScenarioMessage("今天不早了，先这样", "filler_6", "none"))
    msgs.append(ScenarioMessage("再次强调，测试覆盖率全部模块80%", "test_dup", "duplicate"))
    msgs.append(ScenarioMessage("这是质量底线", "test_dup", "none"))

    msgs.append(ScenarioMessage("CI流水线中集成测试", "test_5", "none"))
    msgs.append(ScenarioMessage("每次PR自动运行单元测试和集成测试", "test_5", "none"))
    msgs.append(ScenarioMessage("CI集成测试，PR自动触发", "test_5", "create"))
    msgs.append(ScenarioMessage("测试环境用Docker Compose搭建", "test_6", "none"))
    msgs.append(ScenarioMessage("Docker Compose搭建测试环境", "test_6", "create"))

    # ==================== 场景 6: 部署运维 (~60条) ====================

    msgs.append(ScenarioMessage("部署方案也要讨论一下", "deploy_1", "none"))
    msgs.append(ScenarioMessage("采用蓝绿部署策略", "deploy_1", "none"))
    msgs.append(ScenarioMessage("蓝绿部署可以零停机发布", "deploy_1", "none"))
    msgs.append(ScenarioMessage("部署策略用蓝绿部署", "deploy_1", "create"))

    msgs.append(ScenarioMessage("生产环境用阿里云ACK", "deploy_2", "none"))
    msgs.append(ScenarioMessage("ACK托管K8s集群，减少运维工作量", "deploy_2", "none"))
    msgs.append(ScenarioMessage("生产环境用阿里云ACK托管集群", "deploy_2", "create"))

    msgs.append(ScenarioMessage("CDN用阿里云CDN", "deploy_3", "none"))
    msgs.append(ScenarioMessage("静态资源走CDN加速", "deploy_3", "none"))
    msgs.append(ScenarioMessage("CDN用阿里云CDN", "deploy_3", "create"))

    msgs.append(ScenarioMessage("域名用二级域名区分环境", "deploy_4", "none"))
    msgs.append(ScenarioMessage("dev.xxx.com, staging.xxx.com, prod.xxx.com", "deploy_4", "none"))
    msgs.append(ScenarioMessage("各环境域名确定", "deploy_4", "create"))

    msgs.append(ScenarioMessage("不过蓝绿部署成本较高", "deploy_conflict", "none"))
    msgs.append(ScenarioMessage("灰度发布+滚动更新更适合我们", "deploy_conflict", "none"))
    msgs.append(ScenarioMessage("改为灰度发布+滚动更新", "deploy_conflict", "update"))

    msgs.append(ScenarioMessage("日志收集在部署时一起配置", "deploy_5", "none"))
    msgs.append(ScenarioMessage("Filebeat采集日志，输出到ELK", "deploy_5", "none"))
    msgs.append(ScenarioMessage("日志采集用Filebeat+ELK", "deploy_5", "create"))
    msgs.append(ScenarioMessage("ELK栈确认之前也定过", "deploy_5", "duplicate"))

    msgs.append(ScenarioMessage("备份策略：每天全量+每小时增量", "deploy_6", "none"))
    msgs.append(ScenarioMessage("数据库自动备份到OSS", "deploy_6", "none"))
    msgs.append(ScenarioMessage("备份策略确定", "deploy_6", "create"))
    msgs.append(ScenarioMessage("天气不错，适合写代码", "filler_7", "none"))

    msgs.append(ScenarioMessage("SSL证书用Let's Encrypt", "deploy_7", "none"))
    msgs.append(ScenarioMessage("自动续期，免费", "deploy_7", "none"))
    msgs.append(ScenarioMessage("SSL用Let's Encrypt自动续期", "deploy_7", "create"))

    msgs.append(ScenarioMessage("WAF防护用阿里云WAF", "deploy_8", "none"))
    msgs.append(ScenarioMessage("WAF防御SQL注入和XSS攻击", "deploy_8", "none"))
    msgs.append(ScenarioMessage("WAF用阿里云WAF", "deploy_8", "create"))

    msgs.append(ScenarioMessage("再次确认，部署用灰度发布+滚动更新", "deploy_dup", "duplicate"))
    msgs.append(ScenarioMessage("环境域名已确定", "deploy_dup", "none"))

    # ==================== 场景 7: 安全管理 (~55条) ====================

    msgs.append(ScenarioMessage("安全方面也要重视", "security_1", "none"))
    msgs.append(ScenarioMessage("所有API接口需要鉴权", "security_1", "none"))
    msgs.append(ScenarioMessage("使用JWT做身份认证", "security_1", "none"))
    msgs.append(ScenarioMessage("API鉴权用JWT", "security_1", "create"))

    msgs.append(ScenarioMessage("敏感数据加密存储", "security_2", "none"))
    msgs.append(ScenarioMessage("用户密码用bcrypt哈希", "security_2", "none"))
    msgs.append(ScenarioMessage("数据库连接信息用Vault管理", "security_2", "none"))
    msgs.append(ScenarioMessage("密码bcrypt哈希，密钥Vault管理", "security_2", "create"))

    msgs.append(ScenarioMessage("接口限流用Redis实现", "security_3", "none"))
    msgs.append(ScenarioMessage("令牌桶算法限流", "security_3", "none"))
    msgs.append(ScenarioMessage("Redis令牌桶限流", "security_3", "create"))

    msgs.append(ScenarioMessage("现在安全问题越来越重要", "security_update", "none"))
    msgs.append(ScenarioMessage("还需要增加IP白名单机制", "security_update", "none"))
    msgs.append(ScenarioMessage("增加IP白名单访问控制", "security_update", "update"))

    msgs.append(ScenarioMessage("安全审计日志也需要", "security_4", "none"))
    msgs.append(ScenarioMessage("所有操作记录审计日志", "security_4", "none"))
    msgs.append(ScenarioMessage("操作审计日志记录所有API调用", "security_4", "create"))

    msgs.append(ScenarioMessage("不过JWT过期时间设多久", "security_conflict", "none"))
    msgs.append(ScenarioMessage("Access Token 2小时+Refresh Token 7天", "security_conflict", "none"))
    msgs.append(ScenarioMessage("但这样用户体验不太好", "security_conflict", "none"))
    msgs.append(ScenarioMessage("改为Access Token 24小时，Refresh Token 30天", "security_conflict", "conflict"))

    msgs.append(ScenarioMessage("安全检查清单也要建立", "security_5", "none"))
    msgs.append(ScenarioMessage("上线前必须通过安全检查", "security_5", "none"))
    msgs.append(ScenarioMessage("建立安全检查清单，上线前必检", "security_5", "create"))
    msgs.append(ScenarioMessage("OWASP Top 10都要覆盖", "security_6", "none"))
    msgs.append(ScenarioMessage("OWASP Top 10安全检查全覆盖", "security_6", "create"))
    msgs.append(ScenarioMessage("今晚吃火锅", "filler_8", "none"))

    # ==================== 场景 8: 团队协作 (~55条) ====================

    msgs.append(ScenarioMessage("团队协作方式也需要规范", "team_1", "none"))
    msgs.append(ScenarioMessage("使用Git Flow分支策略", "team_1", "none"))
    msgs.append(ScenarioMessage("develop分支开发，main分支发布", "team_1", "none"))
    msgs.append(ScenarioMessage("feature分支从develop拉取", "team_1", "none"))
    msgs.append(ScenarioMessage("Git Flow分支策略确定", "team_1", "create"))

    msgs.append(ScenarioMessage("PR需要至少一人Review才能合并", "team_2", "none"))
    msgs.append(ScenarioMessage("Reviewer随机分配", "team_2", "none"))
    msgs.append(ScenarioMessage("PR Review机制确定", "team_2", "create"))

    msgs.append(ScenarioMessage("不过Git Flow有点复杂", "team_update", "none"))
    msgs.append(ScenarioMessage("Trunk-based Development更简单", "team_update", "none"))
    msgs.append(ScenarioMessage("改为Trunk-based Development", "team_update", "update"))

    msgs.append(ScenarioMessage("短特性分支，频繁合并到主干", "team_3", "none"))
    msgs.append(ScenarioMessage("特性分支生命周期不超过2天", "team_3", "none"))
    msgs.append(ScenarioMessage("短特性分支策略", "team_3", "create"))
    msgs.append(ScenarioMessage("再来确认一下，Trunk-based Development", "team_dup", "duplicate"))
    msgs.append(ScenarioMessage("短特性分支，频繁合并", "team_dup", "none"))

    msgs.append(ScenarioMessage("Jira管理任务", "team_4", "none"))
    msgs.append(ScenarioMessage("任务状态：待办→进行中→评审→已完成", "team_4", "none"))
    msgs.append(ScenarioMessage("Jira任务管理流程", "team_4", "create"))

    msgs.append(ScenarioMessage("每两周一次回顾会议", "team_5", "none"))
    msgs.append(ScenarioMessage("回顾会议改进流程", "team_5", "none"))
    msgs.append(ScenarioMessage("双周回顾会议", "team_5", "create"))

    msgs.append(ScenarioMessage("文档用飞书文档协作", "team_6", "none"))
    msgs.append(ScenarioMessage("技术方案先写文档再评审", "team_6", "none"))
    msgs.append(ScenarioMessage("飞书文档协作，技术方案先文档后评审", "team_6", "create"))
    msgs.append(ScenarioMessage("今天天气真好，出去走走", "filler_9", "none"))

    msgs.append(ScenarioMessage("知识库用飞书知识库", "team_7", "none"))
    msgs.append(ScenarioMessage("按项目目录组织文档", "team_7", "none"))
    msgs.append(ScenarioMessage("飞书知识库管理文档", "team_7", "create"))
    msgs.append(ScenarioMessage("API文档用Swagger/OpenAPI", "team_8", "none"))
    msgs.append(ScenarioMessage("Swagger自动生成API文档", "team_8", "none"))
    msgs.append(ScenarioMessage("API文档用Swagger自动生成", "team_8", "create"))
    msgs.append(ScenarioMessage("好饿，点个外卖先", "filler_10", "none"))

    # ==================== 场景 9: 技术债务管理 (~30条) ====================

    msgs.append(ScenarioMessage("技术债务也要管理起来", "debt_1", "none"))
    msgs.append(ScenarioMessage("每次迭代预留20%时间处理技术债务", "debt_1", "none"))
    msgs.append(ScenarioMessage("迭代20%时间处理技术债务", "debt_1", "create"))

    msgs.append(ScenarioMessage("老旧代码逐步重构", "debt_2", "none"))
    msgs.append(ScenarioMessage("每次改动相关代码时顺手重构", "debt_2", "none"))
    msgs.append(ScenarioMessage("童子军规则：离开时比来时干净", "debt_2", "none"))
    msgs.append(ScenarioMessage("代码重构采用童子军规则", "debt_2", "create"))

    msgs.append(ScenarioMessage("自动化测试覆盖遗留代码", "debt_3", "none"))
    msgs.append(ScenarioMessage("遗留代码先加测试再重构", "debt_3", "none"))
    msgs.append(ScenarioMessage("遗留代码加测试保护后再重构", "debt_3", "create"))
    msgs.append(ScenarioMessage("这个和之前的测试策略一致", "debt_3", "duplicate"))

    msgs.append(ScenarioMessage("技术债务看板跟踪", "debt_4", "none"))
    msgs.append(ScenarioMessage("按优先级排序技术债务", "debt_4", "none"))
    msgs.append(ScenarioMessage("技术债务看板跟踪", "debt_4", "create"))
    msgs.append(ScenarioMessage("累了一天，下班", "filler_11", "none"))

    # ==================== 场景 10: 扩展填充消息 (~40条) ====================

    msgs.append(ScenarioMessage("晚上加个班，把接口设计做完", "fill_ext", "none"))
    msgs.append(ScenarioMessage("接口设计遵循RESTful规范", "fill_ext", "none"))
    msgs.append(ScenarioMessage("RESTful接口规范确定", "fill_ext", "create"))
    msgs.append(ScenarioMessage("对了，版本控制用URL路径方式", "fill_ext", "none"))
    msgs.append(ScenarioMessage("/v1/, /v2/ 路径版本控制", "fill_ext", "none"))
    msgs.append(ScenarioMessage("API版本控制用URL路径", "fill_ext", "create"))
    msgs.append(ScenarioMessage("分页统一标准", "fill_ext", "none"))
    msgs.append(ScenarioMessage("page+page_size分页", "fill_ext", "none"))
    msgs.append(ScenarioMessage("统一分页标准", "fill_ext", "create"))
    msgs.append(ScenarioMessage("返回格式统一", "fill_ext", "none"))
    msgs.append(ScenarioMessage("{code, message, data}统一返回格式", "fill_ext", "none"))
    msgs.append(ScenarioMessage("统一返回格式确定", "fill_ext", "create"))
    msgs.append(ScenarioMessage("错误码规范也要定", "fill_ext", "none"))
    msgs.append(ScenarioMessage("2xxxx成功，4xxxx客户端错误，5xxxx服务端错误", "fill_ext", "none"))
    msgs.append(ScenarioMessage("错误码规范确定", "fill_ext", "create"))
    msgs.append(ScenarioMessage("国际化方案用react-intl", "fill_ext", "none"))
    msgs.append(ScenarioMessage("react-intl做国际化", "fill_ext", "create"))
    msgs.append(ScenarioMessage("周末了，休息一下", "filler_12", "none"))
    msgs.append(ScenarioMessage("周一重新开始工作", "fill_ext", "none"))
    msgs.append(ScenarioMessage("数据库ORM用Prisma", "fill_ext", "none"))
    msgs.append(ScenarioMessage("Prisma类型安全、开发体验好", "fill_ext", "none"))
    msgs.append(ScenarioMessage("ORM用Prisma", "fill_ext", "create"))
    msgs.append(ScenarioMessage("缓存层用Redis", "fill_ext", "none"))
    msgs.append(ScenarioMessage("Redis做热点数据缓存", "fill_ext", "none"))
    msgs.append(ScenarioMessage("缓存层用Redis", "fill_ext", "create"))
    msgs.append(ScenarioMessage("消息队列用RabbitMQ", "fill_ext", "none"))
    msgs.append(ScenarioMessage("RabbitMQ处理异步任务", "fill_ext", "none"))
    msgs.append(ScenarioMessage("消息队列用RabbitMQ", "fill_ext", "create"))
    msgs.append(ScenarioMessage("搜索服务用Elasticsearch", "fill_ext", "none"))
    msgs.append(ScenarioMessage("Elasticsearch做全文搜索", "fill_ext", "none"))
    msgs.append(ScenarioMessage("搜索用Elasticsearch", "fill_ext", "create"))
    msgs.append(ScenarioMessage("文件存储用OSS", "fill_ext", "none"))
    msgs.append(ScenarioMessage("OSS存储用户上传文件", "fill_ext", "none"))
    msgs.append(ScenarioMessage("文件存储用阿里云OSS", "fill_ext", "create"))
    msgs.append(ScenarioMessage("CDN加速OSS文件访问", "fill_ext", "none"))
    msgs.append(ScenarioMessage("OSS+CDN文件加速方案", "fill_ext", "create"))
    msgs.append(ScenarioMessage("今天就到这里，拜拜", "filler_13", "none"))

    return msgs


# ==================== 消息列表（模块加载时构建） ====================
ALL_MESSAGES: List[ScenarioMessage] = build_messages()
TEST_MESSAGES: List[ScenarioMessage] = ALL_MESSAGES[:2]  # 前2条用于测试