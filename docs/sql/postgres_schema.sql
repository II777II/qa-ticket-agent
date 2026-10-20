-- ============================================================
-- 电商订单 + 知识库 POC：Postgres MVP Schema（15 张表）
--   订单 8 张：order_main / order_item / order_address / payment_order
--              refund_order / inventory / inventory_log / order_status_log
--   知识库 7 张：kb_category / kb_article / kb_article_content / kb_article_version
--                kb_tag / kb_article_tag / kb_article_scope
--
-- POC 当前数据在 backend/data/demo/ecommerce/（JSON + HTML），
-- 本文件是后续切 Postgres 的目标结构；导入器尚未实现。
-- 金额统一 NUMERIC(18,2)，时间统一 TIMESTAMPTZ。
-- ============================================================

-- ---------------- 订单域 ----------------

CREATE TABLE order_main (
  id              BIGINT PRIMARY KEY,
  order_no        VARCHAR(32) NOT NULL UNIQUE,
  user_id         BIGINT NOT NULL,
  order_status    SMALLINT NOT NULL DEFAULT 0
                  CHECK (order_status IN (0, 10, 20, 30, 40, 50, 60, 70)),
  pay_status      SMALLINT NOT NULL DEFAULT 0
                  CHECK (pay_status IN (0, 1, 2, 3)),
  source          SMALLINT NOT NULL DEFAULT 1,
  total_amount    NUMERIC(18, 2) NOT NULL DEFAULT 0,
  discount_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
  freight_amount  NUMERIC(18, 2) NOT NULL DEFAULT 0,
  payable_amount  NUMERIC(18, 2) NOT NULL DEFAULT 0,
  paid_amount     NUMERIC(18, 2) NOT NULL DEFAULT 0,
  refund_amount   NUMERIC(18, 2) NOT NULL DEFAULT 0,
  coupon_id       BIGINT,
  remark          VARCHAR(255),
  expire_time     TIMESTAMPTZ NOT NULL,
  pay_time        TIMESTAMPTZ,
  finish_time     TIMESTAMPTZ,
  cancel_time     TIMESTAMPTZ,
  version         INTEGER NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_order_user_created ON order_main (user_id, created_at DESC);
CREATE INDEX idx_order_status_expire ON order_main (order_status, expire_time);
CREATE INDEX idx_order_pay_time ON order_main (pay_time);

CREATE TABLE order_item (
  id              BIGINT PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES order_main (id),
  order_no        VARCHAR(32) NOT NULL,
  user_id         BIGINT NOT NULL,
  sku_id          BIGINT NOT NULL,
  product_id      BIGINT NOT NULL,
  product_name    VARCHAR(128) NOT NULL,   -- 下单时快照
  sku_spec        VARCHAR(255),
  product_img     VARCHAR(512),
  price           NUMERIC(18, 2) NOT NULL,
  quantity        INTEGER NOT NULL CHECK (quantity > 0),
  item_amount     NUMERIC(18, 2) NOT NULL,
  discount_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
  payable_amount  NUMERIC(18, 2) NOT NULL,
  refund_status   SMALLINT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_item_order ON order_item (order_id);
CREATE INDEX idx_item_sku ON order_item (sku_id);
CREATE INDEX idx_item_user_created ON order_item (user_id, created_at DESC);

CREATE TABLE order_address (
  id             BIGINT PRIMARY KEY,
  order_id       BIGINT NOT NULL UNIQUE REFERENCES order_main (id),
  receiver_name  VARCHAR(64) NOT NULL,
  receiver_phone VARCHAR(32) NOT NULL,
  province       VARCHAR(64) NOT NULL,
  city           VARCHAR(64) NOT NULL,
  district       VARCHAR(64) NOT NULL,
  detail_address VARCHAR(255) NOT NULL,
  postal_code    VARCHAR(16),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payment_order (
  id             BIGINT PRIMARY KEY,
  payment_no     VARCHAR(64) NOT NULL UNIQUE,
  order_id       BIGINT NOT NULL REFERENCES order_main (id),
  order_no       VARCHAR(32) NOT NULL,
  user_id        BIGINT NOT NULL,
  channel        SMALLINT NOT NULL,          -- 1 微信 2 支付宝 3 余额
  out_trade_no   VARCHAR(64),
  amount         NUMERIC(18, 2) NOT NULL,
  status         SMALLINT NOT NULL DEFAULT 0,
  idempotent_key VARCHAR(64) NOT NULL UNIQUE,
  paid_at        TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (channel, out_trade_no)
);
CREATE INDEX idx_payment_order ON payment_order (order_id);

CREATE TABLE refund_order (
  id                 BIGINT PRIMARY KEY,
  refund_no          VARCHAR(64) NOT NULL UNIQUE,
  order_id           BIGINT NOT NULL REFERENCES order_main (id),
  order_no           VARCHAR(32) NOT NULL,
  payment_id         BIGINT NOT NULL REFERENCES payment_order (id),
  user_id            BIGINT NOT NULL,
  amount             NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
  reason             VARCHAR(255),
  status             SMALLINT NOT NULL DEFAULT 0,
  channel_refund_no  VARCHAR(64),
  idempotent_key     VARCHAR(64) NOT NULL UNIQUE,
  refunded_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refund_order ON refund_order (order_id);
CREATE INDEX idx_refund_payment ON refund_order (payment_id);

CREATE TABLE inventory (
  sku_id          BIGINT PRIMARY KEY,
  total_stock     INTEGER NOT NULL DEFAULT 0,
  available_stock INTEGER NOT NULL DEFAULT 0,
  locked_stock    INTEGER NOT NULL DEFAULT 0,
  version         INTEGER NOT NULL DEFAULT 0,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory_log (
  id             BIGSERIAL PRIMARY KEY,
  sku_id         BIGINT NOT NULL,
  order_no       VARCHAR(32),
  biz_type       SMALLINT NOT NULL,           -- 1 预占 2 扣减 3 释放 4 回补
  change_stock   INTEGER NOT NULL,
  before_stock   INTEGER NOT NULL,
  after_stock    INTEGER NOT NULL,
  idempotent_key VARCHAR(64) NOT NULL UNIQUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inventory_log_sku ON inventory_log (sku_id, created_at DESC);
CREATE INDEX idx_inventory_log_order ON inventory_log (order_no);

CREATE TABLE order_status_log (
  id            BIGSERIAL PRIMARY KEY,
  order_id      BIGINT NOT NULL REFERENCES order_main (id),
  order_no      VARCHAR(32) NOT NULL,
  from_status   SMALLINT NOT NULL,
  to_status     SMALLINT NOT NULL,
  operator_type SMALLINT NOT NULL,             -- 1 用户 2 系统 3 管理员
  operator_id   BIGINT,
  remark        VARCHAR(255),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_status_log_order ON order_status_log (order_id);
CREATE INDEX idx_status_log_no ON order_status_log (order_no);

-- ---------------- 知识库域 ----------------

CREATE TABLE kb_category (
  id         BIGINT PRIMARY KEY,
  parent_id  BIGINT NOT NULL DEFAULT 0,
  name       VARCHAR(64) NOT NULL,
  code       VARCHAR(64) NOT NULL UNIQUE,
  level      SMALLINT NOT NULL DEFAULT 1,
  path       VARCHAR(512) NOT NULL DEFAULT '',
  sort_no    INTEGER NOT NULL DEFAULT 0,
  status     SMALLINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE kb_article (
  id             BIGINT PRIMARY KEY,
  article_no     VARCHAR(32) NOT NULL UNIQUE,
  title          VARCHAR(200) NOT NULL,
  summary        VARCHAR(500),
  category_id    BIGINT NOT NULL REFERENCES kb_category (id),
  article_type   SMALLINT NOT NULL DEFAULT 1,
  status         SMALLINT NOT NULL DEFAULT 2,
  visibility     SMALLINT NOT NULL DEFAULT 0,
  author_id      BIGINT NOT NULL,
  reviewer_id    BIGINT,
  current_version_id BIGINT,
  version_no     INTEGER NOT NULL DEFAULT 1,
  is_top         SMALLINT NOT NULL DEFAULT 0,
  sort_weight    INTEGER NOT NULL DEFAULT 0,
  publish_time   TIMESTAMPTZ,
  expire_time    TIMESTAMPTZ,
  view_count     BIGINT NOT NULL DEFAULT 0,
  helpful_count  BIGINT NOT NULL DEFAULT 0,
  unhelpful_count BIGINT NOT NULL DEFAULT 0,
  deleted        SMALLINT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_kb_article_category ON kb_article (category_id, status, deleted);
CREATE INDEX idx_kb_article_publish ON kb_article (publish_time DESC);

CREATE TABLE kb_article_content (
  article_id     BIGINT PRIMARY KEY REFERENCES kb_article (id),
  content        TEXT NOT NULL,               -- 原文 HTML
  content_text   TEXT,                        -- 去标签纯文本，供检索
  content_format SMALLINT NOT NULL DEFAULT 2, -- 1 Markdown 2 HTML 3 富文本
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE kb_article_version (
  id          BIGINT PRIMARY KEY,
  article_id  BIGINT NOT NULL REFERENCES kb_article (id),
  version_no  INTEGER NOT NULL,
  title       VARCHAR(200) NOT NULL,
  summary     VARCHAR(500),
  content     TEXT NOT NULL,
  content_text TEXT,
  content_format SMALLINT NOT NULL DEFAULT 2,
  change_log  VARCHAR(500),
  editor_id   BIGINT NOT NULL,
  status      SMALLINT NOT NULL DEFAULT 2,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (article_id, version_no)
);

CREATE TABLE kb_tag (
  id         BIGINT PRIMARY KEY,
  name       VARCHAR(64) NOT NULL,
  tag_type   SMALLINT NOT NULL DEFAULT 1,
  status     SMALLINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, tag_type)
);

CREATE TABLE kb_article_tag (
  article_id BIGINT NOT NULL REFERENCES kb_article (id),
  tag_id     BIGINT NOT NULL REFERENCES kb_tag (id),
  PRIMARY KEY (article_id, tag_id)
);
CREATE INDEX idx_kb_article_tag_tag ON kb_article_tag (tag_id, article_id);

CREATE TABLE kb_article_scope (
  id         BIGSERIAL PRIMARY KEY,
  article_id BIGINT NOT NULL REFERENCES kb_article (id),
  scope_type SMALLINT NOT NULL,               -- 1 全员 2 部门 3 角色 4 用户 5 商家
  scope_id   BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (article_id, scope_type, scope_id)
);
CREATE INDEX idx_kb_scope ON kb_article_scope (scope_type, scope_id);
