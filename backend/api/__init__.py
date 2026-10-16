"""接口层：HTTP / SSE 适配与请求响应模型。

    app.py           应用组装（中间件、路由注册、静态托管、生命周期）
    deps.py          依赖取用点（从 app.state 取运行时与用例对象）
    routes/          按资源拆分的路由：chat（对话）、tickets（工单）、system（健康检查与首页）
    schemas.py       请求/响应模型与 SSE 编码

这一层刻意保持薄：不写业务规则，只把 HTTP 语义翻译成对应用层的调用。
"""
