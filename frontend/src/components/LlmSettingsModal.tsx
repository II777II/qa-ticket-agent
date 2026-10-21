import { useEffect, useState } from "react";
import { KeyOutlined } from "@ant-design/icons";
import { Alert, Button, Input, Modal, Select, Space, Typography, message } from "antd";

import { configureLlm } from "../api/agent";
import type { AgentInfo } from "../types";

const { Text } = Typography;

export interface LlmSettingsModalProps {
  open: boolean;
  info: AgentInfo | null;
  onClose: () => void;
  onSaved: () => void;
}

/** API Key 只保存在后端进程内存；关闭后前端立即清空输入。 */
export default function LlmSettingsModal({ open, info, onClose, onSaved }: LlmSettingsModalProps) {
  const [provider, setProvider] = useState<"mock" | "deepseek" | "openai">("deepseek");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const current = info?.provider === "deepseek" || info?.provider === "openai" ? info.provider : "deepseek";
    setProvider(current);
    setModel(info?.model === "mock" ? "" : info?.model ?? "");
    setBaseUrl("");
    setApiKey("");
    setError("");
  }, [open, info?.provider, info?.model]);

  const close = () => {
    setApiKey("");
    onClose();
  };

  const save = async () => {
    if (provider !== "mock" && apiKey.trim().length < 8) {
      setError("请输入有效的 API Key");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await configureLlm({
        provider,
        api_key: provider === "mock" ? undefined : apiKey.trim(),
        model: model.trim(),
        base_url: baseUrl.trim(),
      });
      setApiKey("");
      message.success(provider === "mock" ? "已恢复演示模式" : "API Key 验证成功，模型已切换");
      onSaved();
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "模型配置失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={<Space><KeyOutlined />模型 API 设置</Space>}
      open={open}
      onCancel={close}
      width={520}
      footer={[
        <Button key="cancel" onClick={close}>取消</Button>,
        <Button key="save" type="primary" loading={saving} onClick={() => void save()}>保存并测试</Button>,
      ]}
    >
      <Space direction="vertical" size={14} style={{ width: "100%" }}>
        {error && <Alert type="error" showIcon message={error} />}
        <div>
          <Text strong>模型提供方</Text>
          <Select
            value={provider}
            onChange={setProvider}
            style={{ width: "100%", marginTop: 6 }}
            options={[
              { value: "deepseek", label: "DeepSeek" },
              { value: "openai", label: "OpenAI" },
              { value: "mock", label: "Mock 演示模式（无需 Key）" },
            ]}
          />
        </div>
        <div>
          <Text strong>API Key</Text>
          <Input.Password
            value={apiKey}
            disabled={provider === "mock"}
            autoComplete="new-password"
            placeholder={provider === "mock" ? "演示模式无需 API Key" : "sk-..."}
            onChange={(event) => setApiKey(event.target.value)}
            style={{ marginTop: 6 }}
          />
        </div>
        <div>
          <Text strong>模型名称（可选）</Text>
          <Input
            value={model}
            placeholder={provider === "openai" ? "gpt-4o-mini" : "deepseek-chat"}
            onChange={(event) => setModel(event.target.value)}
            style={{ marginTop: 6 }}
          />
        </div>
        <div>
          <Text strong>API Base URL（可选）</Text>
          <Input
            value={baseUrl}
            placeholder="留空使用默认地址"
            onChange={(event) => setBaseUrl(event.target.value)}
            style={{ marginTop: 6 }}
          />
        </div>
        <Alert
          type="info"
          showIcon
          message="Key 仅保存在当前后端进程内存"
          description="不会写入 .env、localStorage 或日志；后端重启后自动清除。"
        />
      </Space>
    </Modal>
  );
}
