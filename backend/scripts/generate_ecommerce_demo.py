"""生成电商订单 + 知识库演示数据（50 订单 / 50 篇 HTML 知识页）。

设计目标：
1. 现在落 JSON + HTML，字段按 Postgres 表形状组织，后续可直接灌库；
2. 数据自洽：金额恒等式、状态机、支付/退款/日志互相对应；
3. 固定随机种子，重复生成结果一致。

用法（项目根目录）：
    python -m backend.scripts.generate_ecommerce_demo
    python -m backend.scripts.generate_ecommerce_demo --out backend/data/demo/ecommerce
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from backend.scripts.ecommerce_topics import CATEGORIES, TOPICS

SEED = 20261021
BASE_TIME = datetime(2026, 10, 21, 12, 0, 0)

PRODUCTS = [
    (101, 1, "无线降噪耳机 Pro", "曜石黑 / 主动降噪", 899.00, "数码"),
    (102, 1, "机械键盘 K87", "茶轴 / 三模", 329.00, "数码"),
    (103, 1, "27 英寸 4K 显示器", "IPS / 75Hz", 1599.00, "数码"),
    (104, 2, "便携充电宝 20000mAh", "65W 快充", 199.00, "数码"),
    (105, 2, "智能手表 S2", "46mm / 蓝牙通话", 1299.00, "数码"),
    (106, 2, "桌面显示器支架", "铝合金 / 单臂", 259.00, "办公"),
    (107, 3, "人体工学椅", "网布 / 带腰托", 1899.00, "家具"),
    (108, 3, "升降办公桌", "1.4m / 双电机", 2399.00, "家具"),
    (109, 3, "护眼台灯", "无极调光", 269.00, "家居"),
    (110, 4, "纯棉四件套", "1.8m / 雾霾蓝", 499.00, "家居"),
    (111, 4, "乳胶枕", "标准高度", 239.00, "家居"),
    (112, 5, "轻量跑鞋", "42 码 / 黑灰", 469.00, "运动"),
    (113, 5, "速干运动 T 恤", "L / 藏青", 129.00, "运动"),
    (114, 5, "瑜伽垫", "10mm / 防滑", 159.00, "运动"),
    (115, 6, "咖啡豆 500g", "中度烘焙", 89.00, "食品"),
    (116, 6, "挂耳咖啡 20 包", "拼配", 69.00, "食品"),
    (117, 7, "保温杯 500ml", "316 不锈钢", 139.00, "生活"),
    (118, 7, "电动牙刷", "声波 / 3 档", 299.00, "生活"),
    (119, 7, "吹风机", "负离子 / 恒温", 399.00, "生活"),
    (120, 8, "双肩背包", "15.6 寸电脑仓", 349.00, "箱包"),
    (121, 8, "登机箱 20 寸", "PC 硬壳", 599.00, "箱包"),
    (122, 9, "男士衬衫", "L / 浅蓝", 259.00, "服饰"),
    (123, 9, "女士风衣", "M / 卡其", 699.00, "服饰"),
    (124, 9, "休闲长裤", "32 码 / 深灰", 229.00, "服饰"),
    (125, 10, "智能音箱 Mini", "语音助手", 249.00, "数码"),
    (126, 10, "路由器 AX3000", "Wi-Fi 6", 399.00, "数码"),
    (127, 11, "扫地机器人", "激光导航 / 自动集尘", 2299.00, "家电"),
    (128, 11, "空气净化器", "除甲醛 / 静音", 1199.00, "家电"),
    (129, 12, "猫粮 2kg", "成猫 / 鸡肉味", 159.00, "宠物"),
    (130, 12, "宠物饮水机", "2L / 静音", 199.00, "宠物"),
]

USERS = [
    (10001, "张三", "138****2301", "上海市", "上海市", "浦东新区", "张江路 88 号 3 栋 1201"),
    (10002, "李四", "139****7712", "北京市", "北京市", "朝阳区", "望京街 12 号 5 单元 802"),
    (10003, "王五", "136****8820", "广东省", "深圳市", "南山区", "科技园南路 66 号 A 座 1506"),
    (10004, "赵六", "137****4519", "浙江省", "杭州市", "西湖区", "文三路 90 号 2 幢 601"),
    (10005, "陈七", "135****9033", "江苏省", "南京市", "鼓楼区", "中山北路 28 号 9 楼"),
    (10006, "刘八", "133****1207", "四川省", "成都市", "高新区", "天府大道 1700 号 3 栋 2203"),
    (10007, "周九", "131****6648", "湖北省", "武汉市", "洪山区", "光谷大道 77 号 6 楼"),
    (10008, "吴十", "158****3391", "山东省", "青岛市", "市南区", "香港中路 10 号 1802"),
    (10009, "郑一", "159****7750", "福建省", "厦门市", "思明区", "软件园二期 21 号 503"),
    (10010, "孙二", "150****2184", "陕西省", "西安市", "雁塔区", "高新四路 9 号 1 单元 1104"),
    (10011, "钱三", "186****4526", "重庆市", "重庆市", "渝北区", "金开大道 100 号 5 栋 802"),
    (10012, "冯四", "185****6692", "天津市", "天津市", "南开区", "卫津路 92 号 3 楼"),
    (10013, "褚五", "188****3310", "湖南省", "长沙市", "岳麓区", "麓谷大道 27 号 6 楼"),
    (10014, "卫六", "189****8807", "河南省", "郑州市", "金水区", "花园路 39 号 1203"),
    (10015, "蒋七", "152****1145", "辽宁省", "沈阳市", "和平区", "青年大街 55 号 2001"),
    (10016, "沈八", "156****7783", "安徽省", "合肥市", "蜀山区", "黄山路 199 号 7 楼"),
    (10017, "韩九", "187****9021", "福建省", "福州市", "鼓楼区", "五四路 137 号 9 楼"),
    (10018, "杨十", "132****6640", "云南省", "昆明市", "五华区", "人民中路 33 号 4 楼"),
    (10019, "朱一", "155****1198", "广西壮族自治区", "南宁市", "青秀区", "民族大道 88 号 12 楼"),
    (10020, "秦二", "180****4409", "江西省", "南昌市", "红谷滩区", "凤凰洲大道 6 号 3 栋"),
]

# 50 条订单的状态分布（0/10/20/30/40/50/60/70）
STATUS_PLAN = [0] * 5 + [10] * 8 + [20] * 8 + [30] * 12 + [40] * 10 + [50] * 3 + [60] * 2 + [70] * 2
PAY_CHANNELS = {1: "微信", 2: "支付宝", 3: "余额"}
REFUND_REASONS = ["尺寸不合适", "商品与描述不符", "质量问题", "不想要了", "物流太慢"]


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def iso(moment: datetime | None) -> str | None:
    return moment.strftime("%Y-%m-%d %H:%M:%S") if moment else None


def split_address(user: tuple) -> dict:
    _, name, phone, province, city, district, detail = user
    return {
        "receiver_name": name,
        "receiver_phone": phone,
        "province": province,
        "city": city,
        "district": district,
        "detail_address": detail,
        "postal_code": "",
    }


def build_orders(rng: random.Random) -> dict[str, list[dict]]:
    order_main: list[dict] = []
    order_items: list[dict] = []
    addresses: list[dict] = []
    payments: list[dict] = []
    refunds: list[dict] = []
    status_logs: list[dict] = []
    inventory_logs: list[dict] = []
    aggregates: list[dict] = []

    item_seq = 0
    payment_seq = 0
    refund_seq = 0
    log_seq = 0
    stock_seq = 0

    for index, status in enumerate(STATUS_PLAN, start=1):
        user = USERS[index % len(USERS)]
        user_id = user[0]
        created = BASE_TIME - timedelta(
            days=rng.randint(0, 59), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
        )
        order_id = 1900000000000000000 + index * 1000
        order_no = f"SO{created:%Y%m%d}{index:04d}"
        expire = created + timedelta(minutes=30)

        chosen = rng.sample(PRODUCTS, rng.randint(1, 3))
        items = []
        total = 0.0
        for sku_id, product_id, name, spec, price, category in chosen:
            quantity = rng.randint(1, 3)
            amount = money(price * quantity)
            total += amount
            items.append(
                {
                    "sku_id": sku_id,
                    "product_id": product_id,
                    "product_name": name,
                    "sku_spec": spec,
                    "product_img": f"/img/sku-{sku_id}.jpg",
                    "price": price,
                    "quantity": quantity,
                    "item_amount": amount,
                    "category": category,
                }
            )
        total = money(total)

        discount = 0.0
        coupon_id = None
        if total >= 100:
            discount = money(rng.choice([0, 5, 10, 20, 30]))
        if discount:
            coupon_id = rng.randint(1001, 1005)
        freight = 0.0 if total >= 99 else 8.0
        payable = money(total - discount + freight)

        pay_status = {0: 0, 10: 1, 20: 1, 30: 1, 40: 1, 50: 0, 60: 2, 70: 3}[status]
        paid_amount = 0.0
        refund_amount = 0.0
        pay_time = None
        finish_time = None
        cancel_time = None

        transitions: list[tuple[datetime, int, int, int, str]] = [
            (created, 0, 0, 1, "创建订单")
        ]

        if status in (10, 20, 30, 40, 60, 70):
            pay_time = created + timedelta(minutes=rng.randint(1, 25))
            paid_amount = payable
            transitions.append((pay_time, 0, 10, 1, "支付成功"))
            if status == 20:
                transitions.append((pay_time + timedelta(minutes=rng.randint(5, 180)), 10, 20, 2, "支付完成，进入待发货"))
            if status in (30, 40, 60, 70):
                ship_time = pay_time + timedelta(hours=rng.randint(6, 72))
                transitions.append((ship_time, 20, 30, 2, "商家已发货"))
            if status == 40:
                finish_time = pay_time + timedelta(days=rng.randint(3, 8))
                transitions.append((finish_time, 30, 40, 1, "确认收货，订单完成"))
            if status in (60, 70):
                refund_time = pay_time + timedelta(days=rng.randint(1, 5))
                transitions.append((refund_time, 40, 60, 1, "用户申请退款"))
                refund_amount = money(payable if status == 70 else payable * 0.4)
                if status == 70:
                    transitions.append((refund_time + timedelta(days=1), 60, 70, 2, "退款成功"))
        elif status == 50:
            cancel_time = created + timedelta(minutes=rng.randint(1, 29))
            transitions.append((cancel_time, 0, 50, 1, "用户取消订单"))

        for moment, from_status, to_status, operator, remark in transitions:
            log_seq += 1
            status_logs.append(
                {
                    "id": log_seq,
                    "order_id": order_id,
                    "order_no": order_no,
                    "from_status": from_status,
                    "to_status": to_status,
                    "operator_type": operator,
                    "operator_id": user_id if operator == 1 else None,
                    "remark": remark,
                    "created_at": iso(moment),
                }
            )

        if pay_time:
            payment_seq += 1
            channel = rng.randint(1, 3)
            payments.append(
                {
                    "id": 2900000000000000000 + payment_seq,
                    "payment_no": f"PAY{created:%Y%m%d}{payment_seq:06d}",
                    "order_id": order_id,
                    "order_no": order_no,
                    "user_id": user_id,
                    "channel": channel,
                    "channel_name": PAY_CHANNELS[channel],
                    "out_trade_no": f"{channel}{created:%Y%m%d}{rng.randint(100000000, 999999999)}",
                    "amount": payable,
                    "status": 5 if status == 70 else 1,
                    "idempotent_key": f"{order_no}:pay",
                    "paid_at": iso(pay_time),
                    "created_at": iso(pay_time),
                    "updated_at": iso(pay_time),
                }
            )

        if status in (60, 70):
            refund_seq += 1
            refunds.append(
                {
                    "id": 3900000000000000000 + refund_seq,
                    "refund_no": f"RF{created:%Y%m%d}{refund_seq:06d}",
                    "order_id": order_id,
                    "order_no": order_no,
                    "payment_id": 2900000000000000000 + payment_seq,
                    "user_id": user_id,
                    "amount": refund_amount,
                    "reason": rng.choice(REFUND_REASONS),
                    "status": 2 if status == 70 else 1,
                    "channel_refund_no": f"CR{created:%Y%m%d}{refund_seq:06d}",
                    "idempotent_key": f"{order_no}:refund",
                    "refunded_at": iso(pay_time + timedelta(days=2)) if status == 70 else None,
                    "created_at": iso(pay_time + timedelta(days=1)),
                    "updated_at": iso(pay_time + timedelta(days=2) if status == 70 else pay_time + timedelta(days=1)),
                }
            )

        remaining_discount = discount
        for position, item in enumerate(items):
            item_seq += 1
            if position == len(items) - 1:
                item_discount = money(remaining_discount)
            else:
                item_discount = money(discount * item["item_amount"] / total)
                remaining_discount = money(remaining_discount - item_discount)
            order_items.append(
                {
                    "id": 1900000000001000000 + item_seq,
                    "order_id": order_id,
                    "order_no": order_no,
                    "user_id": user_id,
                    "sku_id": item["sku_id"],
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "sku_spec": item["sku_spec"],
                    "product_img": item["product_img"],
                    "price": item["price"],
                    "quantity": item["quantity"],
                    "item_amount": item["item_amount"],
                    "discount_amount": item_discount,
                    "payable_amount": money(item["item_amount"] - item_discount),
                    "refund_status": 0,
                    "created_at": iso(created),
                }
            )
            stock_seq += 1
            inventory_logs.append(
                {
                    "id": stock_seq,
                    "sku_id": item["sku_id"],
                    "order_no": order_no,
                    "biz_type": 1,
                    "change_stock": -item["quantity"],
                    "before_stock": 200 + item["sku_id"],
                    "after_stock": 200 + item["sku_id"] - item["quantity"],
                    "idempotent_key": f"{order_no}:{item['sku_id']}:reserve",
                    "created_at": iso(created),
                }
            )
            if status == 50:
                stock_seq += 1
                inventory_logs.append(
                    {
                        "id": stock_seq,
                        "sku_id": item["sku_id"],
                        "order_no": order_no,
                        "biz_type": 3,
                        "change_stock": item["quantity"],
                        "before_stock": 200 + item["sku_id"] - item["quantity"],
                        "after_stock": 200 + item["sku_id"],
                        "idempotent_key": f"{order_no}:{item['sku_id']}:release",
                        "created_at": iso(cancel_time),
                    }
                )

        address = split_address(user)
        addresses.append(
            {
                "id": 1900000000002000000 + index,
                "order_id": order_id,
                **address,
                "created_at": iso(created),
            }
        )

        order = {
            "id": order_id,
            "order_no": order_no,
            "user_id": user_id,
            "order_status": status,
            "pay_status": pay_status,
            "source": rng.randint(1, 3),
            "total_amount": total,
            "discount_amount": discount,
            "freight_amount": freight,
            "payable_amount": payable,
            "paid_amount": paid_amount,
            "refund_amount": refund_amount,
            "coupon_id": coupon_id,
            "remark": rng.choice(["", "", "", "放门口即可", "工作日送达"]),
            "expire_time": iso(expire),
            "pay_time": iso(pay_time),
            "finish_time": iso(finish_time),
            "cancel_time": iso(cancel_time),
            "version": rng.randint(0, 3),
            "created_at": iso(created),
            "updated_at": iso(finish_time or cancel_time or pay_time or created),
        }
        order_main.append(order)

        aggregates.append(
            {
                **order,
                "user": {"id": user_id, "name": user[1], "phone": user[2]},
                "items": [row for row in order_items if row["order_no"] == order_no],
                "address": address,
                "payments": [p for p in payments if p["order_no"] == order_no],
                "refunds": [r for r in refunds if r["order_no"] == order_no],
                "status_logs": [log for log in status_logs if log["order_no"] == order_no],
            }
        )

    inventory = []
    for sku_id, product_id, name, spec, price, category in PRODUCTS:
        total_stock = 200 + sku_id % 50
        locked = (sku_id % 7) * 3
        inventory.append(
            {
                "sku_id": sku_id,
                "product_id": product_id,
                "product_name": name,
                "spec": spec,
                "price": price,
                "category": category,
                "total_stock": total_stock,
                "available_stock": total_stock - locked,
                "locked_stock": locked,
                "version": 0,
                "updated_at": iso(BASE_TIME),
            }
        )

    return {
        "orders": aggregates,
        "order_main": order_main,
        "order_item": order_items,
        "order_address": addresses,
        "payment_order": payments,
        "refund_order": refunds,
        "order_status_log": status_logs,
        "inventory": inventory,
        "inventory_log": inventory_logs,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="{summary}" />
  <title>{title} - 电商帮助中心</title>
  <style>
    body {{ margin: 0; background: #f7f7f8; color: #1c1c1f; font: 14px/1.75 -apple-system, "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 760px; margin: 40px auto 64px; background: #fff; border: 1px solid #e6e6ea; border-radius: 14px; padding: 28px 32px; }}
    .breadcrumb {{ font-size: 12px; color: #8b8b93; }}
    h1 {{ font-size: 24px; margin: 10px 0 8px; }}
    .meta {{ font-size: 12px; color: #8b8b93; border-bottom: 1px solid #efeff2; padding-bottom: 12px; }}
    .summary {{ background: #f4f8f6; border-left: 3px solid #0d8f6f; padding: 10px 14px; border-radius: 6px; color: #3d4a44; }}
    h2 {{ font-size: 16px; margin: 22px 0 8px; }}
    li {{ margin: 6px 0; }}
    dt {{ font-weight: 600; margin-top: 10px; }}
    dd {{ margin: 4px 0 0; color: #4a4a52; }}
    .note {{ margin-top: 24px; font-size: 12px; color: #9b9ba3; }}
    a {{ color: #0d8f6f; }}
  </style>
</head>
<body data-article-id="{article_no}">
  <div class="page">
    <nav class="breadcrumb"><a href="../index.html">帮助中心</a> / {category_name}</nav>
    <h1>{title}</h1>
    <div class="meta">编号 {article_no} · 分类 {category_name} · 版本 v1 · 更新 {updated_at}</div>
    <p class="summary">{summary}</p>
    <h2>操作步骤 / 规则</h2>
    <ol>{steps}</ol>
    <h2>常见问题</h2>
    <dl>{faqs}</dl>
    <p class="note">本文为演示数据，实际规则以平台正式公告为准。</p>
  </div>
</body>
</html>
"""

CATEGORY_FAQ = {
    "ORDER": [("支付失败会扣款吗？", "未成功的支付不会扣款；如已扣款请保留流水号联系客服。")],
    "DELIVERY": [("多久能看到物流单号？", "发货后系统会同步物流单号，通常 2 小时内更新。")],
    "AFTERSALE": [("售后处理需要多久？", "一般 1–3 个工作日审核，退款到账时间取决于支付渠道。")],
    "INVOICE": [("发票多久能开好？", "电子发票一般 1 个工作日内开具并发送到预留邮箱。")],
    "MEMBER": [("权益会和活动叠加吗？", "以结算页展示为准，部分权益与活动互斥。")],
    "ACCOUNT": [("修改安全设置会影响登录吗？", "会立即生效，其他设备可能需要重新登录。")],
    "PRODUCT": [("支持七天无理由吗？", "支持，需保持商品与包装完好，具体以商品页为准。")],
    "MERCHANT": [("商家不发货怎么办？", "可先催发货，超时未发货可申请退款或平台介入。")],
}

ARTICLE_TYPE = {
    "ORDER": 1, "DELIVERY": 1, "AFTERSALE": 3, "INVOICE": 1,
    "MEMBER": 6, "ACCOUNT": 1, "PRODUCT": 2, "MERCHANT": 7,
}


def build_kb(output_root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    pages_dir = output_root / "kb" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    categories = [
        {
            "id": index,
            "parent_id": 0,
            "name": name,
            "code": code,
            "level": 1,
            "path": f"/{index}/",
            "sort_no": index * 10,
            "status": 1,
            "created_at": iso(BASE_TIME - timedelta(days=120)),
            "updated_at": iso(BASE_TIME),
        }
        for index, (code, name, _) in enumerate(CATEGORIES, start=1)
    ]
    category_by_code = {category["code"]: category for category in categories}

    tag_names: list[str] = []
    articles: list[dict] = []
    for index, (code, title, summary, steps) in enumerate(TOPICS, start=1):
        article_no = f"KB-EC-{index:04d}"
        category = category_by_code[code]
        tags = [category["name"], "帮助中心"]
        if "退款" in title or "退货" in title:
            tags.append("退款")
        if "物流" in title or "发货" in title or "配送" in title:
            tags.append("物流")
        if "发票" in title:
            tags.append("发票")
        if "会员" in title or "优惠" in title:
            tags.append("会员")
        for tag in tags:
            if tag not in tag_names:
                tag_names.append(tag)

        publish = BASE_TIME - timedelta(days=120 - index * 2)
        faqs = list(CATEGORY_FAQ.get(code, [])) + [
            (f"这篇「{title}」适用于所有商品吗？", "通用规则适用于多数商品，特殊品类以商品页说明为准。")
        ]
        html = HTML_TEMPLATE.format(
            article_no=article_no,
            title=title,
            summary=summary,
            category_name=category["name"],
            updated_at=publish.strftime("%Y-%m-%d"),
            steps="".join(f"<li>{step}</li>" for step in steps),
            faqs="".join(f"<dt>{question}</dt><dd>{answer}</dd>" for question, answer in faqs),
        )
        filename = f"{article_no}.html"
        (pages_dir / filename).write_text(html, encoding="utf-8")

        articles.append(
            {
                "id": 5000 + index,
                "article_no": article_no,
                "title": title,
                "summary": summary,
                "category_id": category["id"],
                "category_code": code,
                "category_name": category["name"],
                "article_type": ARTICLE_TYPE[code],
                "tags": tags,
                "status": 2,
                "visibility": 0,
                "author_id": 9001,
                "reviewer_id": 9002,
                "version_no": 1,
                "is_top": 1 if index <= 3 else 0,
                "sort_weight": 100 - index,
                "publish_time": iso(publish),
                "updated_at": iso(publish),
                "path": f"pages/{filename}",
                "url": f"/kb/pages/{filename}",
                "view_count": 100 + index * 7,
                "helpful_count": 10 + index % 17,
                "unhelpful_count": index % 3,
                "deleted": 0,
            }
        )

    tags = [
        {"id": 7000 + index, "name": name, "tag_type": 1, "status": 1, "created_at": iso(BASE_TIME)}
        for index, name in enumerate(tag_names, start=1)
    ]

    # 静态目录页，方便直接浏览 50 篇 HTML
    blocks = []
    for category in categories:
        items = [a for a in articles if a["category_id"] == category["id"]]
        links = "".join(
            f'<li><a href="{a["path"]}">{a["title"]}</a><span>{a["summary"]}</span></li>' for a in items
        )
        blocks.append(f"<section><h2>{category['name']}（{len(items)}）</h2><ul>{links}</ul></section>")
    index_html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8" /><title>电商帮助中心 - 知识库目录</title>
<style>body{{margin:40px auto;max-width:860px;font:14px/1.7 -apple-system,"Microsoft YaHei",sans-serif;color:#1c1c1f;background:#f7f7f8}}
h1{{font-size:22px}}section{{background:#fff;border:1px solid #e6e6ea;border-radius:12px;padding:16px 20px;margin:14px 0}}
li{{margin:8px 0}}a{{color:#0d8f6f;text-decoration:none}}span{{display:block;color:#8b8b93;font-size:12px}}</style></head>
<body><h1>电商帮助中心 · 知识库目录（50 篇）</h1>{''.join(blocks)}</body></html>
"""
    (output_root / "kb" / "index.html").write_text(index_html, encoding="utf-8")
    return articles, categories, tags


def dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成电商订单与知识库演示数据")
    parser.add_argument("--out", default="backend/data/demo/ecommerce", help="输出目录")
    args = parser.parse_args()

    rng = random.Random(SEED)
    output_root = Path(args.out)
    data = build_orders(rng)
    articles, categories, tags = build_kb(output_root)

    dump(output_root / "orders.json", data["orders"])
    tables = output_root / "tables"
    for name in ("order_main", "order_item", "order_address", "payment_order", "refund_order", "order_status_log", "inventory", "inventory_log"):
        dump(tables / f"{name}.json", data[name])
    dump(output_root / "kb" / "articles.json", articles)
    dump(output_root / "kb" / "categories.json", categories)
    dump(output_root / "kb" / "tags.json", tags)

    # ---- 自检 ----
    assert len(data["orders"]) == 50, "订单数必须为 50"
    assert len(articles) == 50, "知识文章必须为 50"
    assert len(list((output_root / "kb" / "pages").glob("*.html"))) == 50
    order_nos = {order["order_no"] for order in data["orders"]}
    for order in data["orders"]:
        assert money(order["total_amount"] - order["discount_amount"] + order["freight_amount"]) == order["payable_amount"]
        assert order["status_logs"], f"{order['order_no']} 缺少状态日志"
        assert order["address"]["receiver_name"]
        assert order["items"]
        if order["order_status"] in (10, 20, 30, 40, 60, 70):
            assert order["payments"], f"{order['order_no']} 缺支付单"
        if order["order_status"] in (60, 70):
            assert order["refunds"], f"{order['order_no']} 缺退款单"
    assert all(item["order_no"] in order_nos for item in data["order_item"])
    for article in articles:
        page = output_root / "kb" / article["path"]
        text = page.read_text(encoding="utf-8")
        assert f'data-article-id="{article["article_no"]}"' in text
        assert "<title>" in text and article["title"] in text

    print(f"订单: {len(data['orders'])} 条（状态分布 {sorted({o['order_status'] for o in data['orders']})}）")
    print(f"明细: {len(data['order_item'])} 行；支付单 {len(data['payment_order'])}；退款单 {len(data['refund_order'])}；状态日志 {len(data['order_status_log'])}")
    print(f"知识库: {len(articles)} 篇 HTML（分类 {len(categories)}，标签 {len(tags)}）")
    print(f"输出目录: {output_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
