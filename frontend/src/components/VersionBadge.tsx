export interface VersionBadgeProps {
  sha?: string;
  date?: string;
}

/** 显示当前 git 短 hash，方便对照「改前 / 改后」版本。 */
export default function VersionBadge({ sha, date }: VersionBadgeProps) {
  return (
    <span className="version-badge" title={date ? `提交时间 ${date}` : "未获取到 git 信息"}>
      git {sha || "unknown"}
    </span>
  );
}
