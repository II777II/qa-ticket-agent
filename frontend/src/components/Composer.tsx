import { Sender } from "@ant-design/x";

export interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onStop?: () => void;
  busy?: boolean;
  model?: string;
  placeholder?: string;
  large?: boolean;
}

/** 输入区：Sender + 模型徽标 + 提示，首页与对话页共用。 */
export default function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy = false,
  model = "Agent",
  placeholder = "描述你遇到的问题…",
  large = false,
}: ComposerProps) {
  return (
    <div className={large ? "composer composer-large" : "composer"}>
      <Sender
        value={value}
        onChange={onChange}
        onSubmit={(text) => onSubmit(text)}
        loading={busy}
        onCancel={onStop}
        placeholder={placeholder}
        autoSize={{ minRows: large ? 2 : 1, maxRows: 6 }}
      />
      <div className="composer-bar">
        <span className="model-pill">{model}</span>
        <span className="composer-hint">Enter 发送 · Shift + Enter 换行</span>
      </div>
    </div>
  );
}
