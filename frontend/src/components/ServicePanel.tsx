import { useState } from "react";
import { Alert, Button, Checkbox, Empty, Input, Select, Space, Tag, Typography } from "antd";

import { confirmService } from "../api/agent";
import type { ServiceConfirmResult, ServiceDraft, ServiceType } from "../types";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const SERVICE_TYPES: ServiceType[] = ["退货", "换货", "维修", "退款", "补发", "价保", "其他"];

const FIELD_LABELS: Record<string, string> = {
  service_type: "业务类型",
  order_no: "订单号",
  contact: "联系人",
  description: "问题描述",
};

export interface ServicePanelProps {
  draft: ServiceDraft | null;
  question: string;
  onUpdate: (draft: ServiceDraft) => void;
}

function missingFields(draft: ServiceDraft): string[] {
  const missing: string[] = [];
  if (!draft.service_type) missing.push("service_type");
  if (!/^SO\d{12}$/i.test(draft.order_no.trim())) missing.push("order_no");
  if (draft.contact.trim().length < 2) missing.push("contact");
  if (draft.description.trim().length < 10) missing.push("description");
  return missing;
}

/** 右侧业务办理草稿：槽位可编辑，信息齐全且用户确认后才提交。 */
export default function ServicePanel({ draft, question, onUpdate }: ServicePanelProps) {
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ServiceConfirmResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!draft) {
    return (
      <aside className="side-panel">
        <div className="panel-head">
          <span className="panel-title">业务办理</span>
          <Tag variant="filled">待识别</Tag>
        </div>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本轮还没有业务办理草稿" />
      </aside>
    );
  }

  const missing = missingFields(draft);
  const ready = missing.length === 0;

  const patch = (partial: Partial<ServiceDraft>) => {
    setChecked(false);
    setResult(null);
    setError(null);
    const next = { ...draft, ...partial };
    const nextMissing = missingFields(next);
    const slots = {
      ...next.slots,
      order_no: next.order_no.trim(),
      contact: next.contact.trim(),
      service_type: next.service_type,
      category: next.category,
    };
    onUpdate({
      ...next,
      title: `${next.service_type || "售后"}办理 · ${next.order_no.trim() || "待补充订单号"}`.slice(0, 60),
      slots: Object.fromEntries(Object.entries(slots).filter(([, value]) => Boolean(value))),
      missing: nextMissing,
      ready: nextMissing.length === 0,
      status: nextMissing.length === 0 ? "ready" : "draft",
    });
  };

  const submit = async () => {
    if (!ready || !checked || !draft.service_type) return;
    setSubmitting(true);
    setError(null);
    try {
      setResult(
        await confirmService({
          order_no: draft.order_no.trim().toUpperCase(),
          contact: draft.contact.trim(),
          service_type: draft.service_type,
          category: draft.category,
          priority: draft.priority,
          description: draft.description.trim(),
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="side-panel">
      <div className="panel-head">
        <span className="panel-title">业务办理</span>
        <Tag color={ready ? "green" : "gold"}>{ready ? "待用户确认" : `缺少 ${missing.length} 项`}</Tag>
        <span className="spacer" />
        <Tag variant="filled">{draft.category}</Tag>
      </div>

      <div className="service-scroll">
        <div className="panel-query">
          <Text type="secondary">本轮描述</Text>
          <div className="query-text">{question || draft.description}</div>
        </div>

        {missing.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message="信息尚未完整"
            description={`请补充：${missing.map((field) => FIELD_LABELS[field] ?? field).join("、")}`}
          />
        )}

        <div className="slot-block">
          <Text type="secondary">已识别槽位</Text>
          <Space size={[6, 6]} wrap>
            {Object.entries(draft.slots)
              .filter(([, value]) => Boolean(value))
              .map(([key, value]) => (
                <Tag key={key} color="cyan">
                  {FIELD_LABELS[key] ?? key}：{value}
                </Tag>
              ))}
          </Space>
        </div>

        <div className="service-field">
          <label htmlFor="service-type">业务类型</label>
          <Select<ServiceType>
            id="service-type"
            value={draft.service_type || undefined}
            placeholder="请选择退货、换货、维修等"
            options={SERVICE_TYPES.map((value) => ({ value, label: value }))}
            onChange={(value) => patch({ service_type: value })}
          />
        </div>

        <div className="service-field">
          <label htmlFor="service-order-no">订单号</label>
          <Input
            id="service-order-no"
            className="mono"
            status={draft.order_no && !/^SO\d{12}$/i.test(draft.order_no.trim()) ? "error" : undefined}
            value={draft.order_no}
            placeholder="SO202609150020"
            onChange={(event) => patch({ order_no: event.target.value.toUpperCase() })}
          />
          <Text type="secondary">必须以 SO 开头，共 14 位。</Text>
        </div>

        <div className="service-field">
          <label htmlFor="service-contact">联系人</label>
          <Input
            id="service-contact"
            value={draft.contact}
            placeholder="手机号或邮箱"
            onChange={(event) => patch({ contact: event.target.value })}
          />
        </div>

        <div className="service-field">
          <label htmlFor="service-description">问题描述</label>
          <TextArea
            id="service-description"
            rows={4}
            value={draft.description}
            onChange={(event) => patch({ description: event.target.value })}
          />
          <Text type="secondary">至少 10 个字，确认后将作为售后工单描述。</Text>
        </div>

        <div className="service-summary">
          <span>优先级：{draft.priority}</span>
          <span>分类：{draft.category}</span>
        </div>

        {result ? (
          <Alert
            type="success"
            showIcon
            message={result.duplicated ? "已返回原工单" : "业务办理已提交"}
            description={
              <Paragraph className="service-result">
                工单号 <span className="mono">{result.ticket_id}</span>，当前状态：{result.status}。
                {result.message}
              </Paragraph>
            }
          />
        ) : (
          <>
            <Checkbox checked={checked} onChange={(event) => setChecked(event.target.checked)}>
              我已核对业务类型、订单号、联系人和问题描述
            </Checkbox>
            {error && <Alert type="error" showIcon message="提交失败" description={error} />}
            <Button
              type="primary"
              block
              disabled={!ready || !checked}
              loading={submitting}
              onClick={() => void submit()}
            >
              确认提交
            </Button>
          </>
        )}
      </div>
    </aside>
  );
}
