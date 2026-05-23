import { Card, Tag, Progress, Space } from "antd";
import {
  ClockCircleOutlined,
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import type { TaskSummary } from "../types";
import { Typography } from "antd";

const { Paragraph } = Typography;
const statusConfig: Record<
  string,
  { color: string; icon: React.ReactNode; label: string }
> = {
  queued: { color: "default", icon: <ClockCircleOutlined />, label: "排队中" },
  running: {
    color: "processing",
    icon: <SyncOutlined spin />,
    label: "运行中",
  },
  completed: {
    color: "success",
    icon: <CheckCircleOutlined />,
    label: "已完成",
  },
  failed: { color: "error", icon: <CloseCircleOutlined />, label: "失败" },
  stopped: { color: "warning", icon: <StopOutlined />, label: "已停止" },
  monitoring: {
    color: "processing",
    icon: <EyeOutlined />,
    label: "监控中",
  },
};

interface Props {
  task: TaskSummary;
  onClick?: () => void;
}

export default function TaskCard({ task, onClick }: Props) {
  const displayStatus =
    task.recurring_interval_minutes && task.recurring_interval_minutes > 0 && task.status === "completed"
      ? "monitoring"
      : task.status;
  const cfg = statusConfig[displayStatus] || statusConfig.queued;
  const pct =
    task.pages_discovered > 0
      ? Math.round((task.pages_crawled / task.pages_discovered) * 100)
      : 0;

  return (
    <Card
      hoverable
      onClick={onClick}
      style={{ margin: "12px 0px", overflow: "hidden" }}
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          <Tag icon={cfg.icon} color={cfg.color}>
            {cfg.label}
          </Tag>
          <Paragraph
            strong
            ellipsis={{
              rows: 2,
              tooltip: task.seed_url,
            }}
          >
            {task.seed_url}
          </Paragraph>
        </Space>
        {task.status === "running" && (
          <Progress percent={pct} size="small" status="active" />
        )}
      </Space>
    </Card>
  );
}
