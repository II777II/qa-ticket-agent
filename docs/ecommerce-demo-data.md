# 电商演示数据（50 订单 + 50 篇知识库 HTML）

## 目录

```
backend/data/demo/ecommerce/
├── orders.json                  # 订单聚合视图（含明细/地址/支付/退款/状态日志）
├── tables/                      # 按 Postgres 表拆分的平面数据
│   ├── order_main.json          # 50 行
│   ├── order_item.json          # 87 行
│   ├── order_address.json       # 50 行
│   ├── payment_order.json       # 42 行
│   ├── refund_order.json        # 4 行
│   ├── order_status_log.json    # 145 行
│   ├── inventory.json           # 30 个 SKU
│   └── inventory_log.json       # 预占/释放流水
└── kb/
    ├── articles.json            # 50 篇文章索引（对应 kb_article）
    ├── categories.json          # 8 个分类
    ├── tags.json                # 13 个标签
    ├── index.html               # 静态目录页
    └── pages/KB-EC-0001.html …  # 50 篇 HTML 正文
```

## 订单分布

| 状态 | 数量 |
| --- | --- |
| 待支付 | 5 |
| 已支付 | 8 |
| 待发货 | 8 |
| 已发货 | 12 |
| 已完成 | 10 |
| 已取消 | 3 |
| 退款中 | 2 |
| 已退款 | 2 |

金额规则：`payable = total - discount + freight`；促销按明细金额比例分摊；已支付/已发货/已完成有支付单，退款中有部分退款单，已退款有全额退款单。

## 知识库

8 个分类：下单与支付、配送与物流、退换与售后、发票与报销、会员与优惠、账户与安全、商品与使用、商家与规则。

每篇 HTML 都是完整页面（内联样式、无外部资源），带 `data-article-id`、`<title>`、摘要、操作步骤与常见问题，可直接在浏览器打开，也可被后端检索器按 `<h2>` 切块召回。

## 重新生成

```powershell
python -m backend.scripts.generate_ecommerce_demo
```

固定随机种子 `20261021`，重复执行输出一致；生成器内置自检（数量、金额恒等式、引用关系、HTML 完整性）。

## 切 Postgres（后续）

1. 按 `docs/sql/postgres_schema.sql` 建 15 张表（订单 8 + 知识库 7）；
2. 在 `infrastructure/storage.py` 增加与 `JsonOrderStore` 同方法的 PostgreSQL 仓储；
3. `.env` 设置 `ORDER_STORE=postgres`，订单查询接口与页面不用改；
4. 知识库正文入库到 `kb_article_content.content`，纯文本写 `content_text`；
5. 导入脚本把 `tables/*.json` 映射到同名表，`kb/articles.json` + 页面内容写入 `kb_article` / `kb_article_content`。

当前 POC 没有连库：订单读取 `orders.json`，知识库读取 HTML 页面，接口与前端已按最终结构设计。
