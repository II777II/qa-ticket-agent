"""问答工单 Agent POC - 后端包。

分层（依赖方向单向：api → application → domain，infrastructure 由 application 注入）：

    domain/          领域层：工单实体、分类/优先级/状态规则、重复建单判定、领域异常
    application/     应用层：运行时装配 + 用例（agent 编排 / 对话 / 工单）
    infrastructure/  基础设施层：配置、日志、模型、检索、工单存储的实现与工厂
    api/             接口层：FastAPI 组装、路由、请求响应模型与 SSE 编码

    data/            知识库文档与工单落盘（跨层的资源，不属于任何一层）
    scripts/         命令行脚本（验收、画结构图）
    tests/           测试

对外叙述时常说成「五层」：表现层是独立的 frontend/，其余四层都在 backend/ 里
（详见 docs/architecture.md 的映射表）。
"""
