import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Typography, Tag, Descriptions, App, Popconfirm, Spin, Card, Tabs,
} from "antd";
import { ArrowLeftOutlined, DeleteOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import { useWebSocket } from "../hooks/useWebSocket";
import DataTable from "../components/DataTable";
import InsightCharts from "../components/InsightCharts";
import ChangeTrendChart from "../components/ChangeTrendChart";
import type {
  TaskDetail as TaskDetailType,
  ExtractedRecord,
  DataInsight,
  ContentChange,
  TrackingStat,
} from "../types";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  queued: "default",
  running: "processing",
  completed: "success",
  failed: "error",
  stopped: "warning",
  monitoring: "processing",
};

const statusLabels: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
  monitoring: "监控中",
};

function getDisplayStatus(task: TaskDetailType | null, status: string): string {
  if (task?.recurring_interval_minutes && task.recurring_interval_minutes > 0 && status === "completed") {
    return "monitoring";
  }
  return status;
}

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [task, setTask] = useState<TaskDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [extractedData, setExtractedData] = useState<ExtractedRecord[]>([]);
  const [pagesCrawled, setPagesCrawled] = useState(0);
  const [pagesDiscovered, setPagesDiscovered] = useState(0);
  const [resultCount, setResultCount] = useState(0);
  const [status, setStatus] = useState<string>("");
  const [insights, setInsights] = useState<DataInsight[]>([]);
  const [trackingChanges, setTrackingChanges] = useState<ContentChange[]>([]);
  const [trackingStats, setTrackingStats] = useState<TrackingStat[]>([]);

  const { lastMessage, connected, insights: wsInsights, changes: wsChanges } = useWebSocket(
    status === "running" || status === "queued" ? taskId : undefined
  );

  const fetchTask = useCallback(async () => {
    if (!taskId) return;
    try {
      const data = await api.getTask(taskId);
      setTask(data);
      setStatus(data.status);
      setPagesCrawled(data.pages_crawled);
      setPagesDiscovered(data.pages_discovered);
      setResultCount(data.result_count);
      if (data.results?.length) {
        setExtractedData(data.results);
      }
      if (data.insights) {
        setInsights(data.insights);
      }
    } catch {
      message.error("获取任务详情失败");
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  const fetchTrackingData = useCallback(async () => {
    if (!task?.task_group_id) return;
    try {
      const [changes, stats] = await Promise.all([
        api.getChanges(task.task_group_id),
        api.getTrackingStats(task.task_group_id),
      ]);
      setTrackingChanges(changes);
      setTrackingStats(stats);
    } catch {
      // tracking data is optional
    }
  }, [task?.task_group_id]);

  useEffect(() => {
    fetchTask();
  }, [fetchTask]);

  useEffect(() => {
    if (task?.task_group_id) {
      fetchTrackingData();
    }
  }, [fetchTrackingData, task?.task_group_id]);

  // Sync WebSocket insights
  useEffect(() => {
    if (wsInsights.length > 0) {
      setInsights(wsInsights);
    }
  }, [wsInsights]);

  // Sync WebSocket changes
  useEffect(() => {
    if (wsChanges.length > 0) {
      setTrackingChanges(wsChanges);
    }
  }, [wsChanges]);

  // WebSocket 实时更新
  useEffect(() => {
    if (!lastMessage) return;
    setPagesCrawled(lastMessage.pages_crawled);
    setPagesDiscovered(lastMessage.pages_discovered);

    if (lastMessage.type === "data_extracted" && lastMessage.items) {
      const newRecords: ExtractedRecord[] = lastMessage.items.map((item) => ({
        source_url: lastMessage.url || "",
        data: item,
      }));
      setExtractedData((prev) => [...prev, ...newRecords]);
      setResultCount((prev) => prev + lastMessage.items!.length);
    }

    if (lastMessage.type === "completed" || lastMessage.type === "error") {
      // 监控任务不直接标记为完成，等待 API 返回准确状态
      if (task?.recurring_interval_minutes && task.recurring_interval_minutes > 0) {
        fetchTask();
      } else {
        setStatus(lastMessage.type === "completed" ? "completed" : "failed");
        setTimeout(fetchTask, 500);
      }
    }
  }, [lastMessage, fetchTask]);

  const handleDelete = async () => {
    if (!taskId) return;
    try {
      await api.deleteTask(taskId);
      message.success("任务已停止");
      setStatus("stopped");
      navigate("/");
    } catch {
      message.error("操作失败");
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", marginTop: 80 }}>
        <Spin tip="加载中...">
          <div style={{ height: 40 }} />
        </Spin>
      </div>
    );
  }

  if (!task) {
    return <div>任务不存在</div>;
  }

  const showMonitoring = task.recurring_interval_minutes > 0;

  const tabItems = [
    {
      key: "results",
      label: "爬取结果",
      children: (
        <div>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="种子 URL">{task.seed_url}</Descriptions.Item>
              <Descriptions.Item label="数据描述">{task.data_description}</Descriptions.Item>
              <Descriptions.Item label="最大深度">{task.max_depth}</Descriptions.Item>
              <Descriptions.Item label="最大页数">{task.max_pages}</Descriptions.Item>
              <Descriptions.Item label="JS 渲染">{task.use_javascript ? "是" : "否"}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{task.created_at}</Descriptions.Item>
              {showMonitoring && (
                <Descriptions.Item label="监控间隔">
                  {task.recurring_interval_minutes} 分钟
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>

          {task.error_message && (
            <Card size="small" style={{ marginBottom: 16, borderColor: "#ff4d4f" }}>
              <Typography.Text type="danger">{task.error_message}</Typography.Text>
            </Card>
          )}

          <Space style={{ marginBottom: 16 }}>
            <Title level={4} style={{ margin: 0 }}>提取数据 ({extractedData.length} 条)</Title>
            {(status === "running" || status === "queued") && (
              <Popconfirm title="确认停止此任务？" onConfirm={handleDelete}>
                <Button danger icon={<DeleteOutlined />}>停止任务</Button>
              </Popconfirm>
            )}
          </Space>

          <Card>
            <DataTable data={extractedData} />
          </Card>
        </div>
      ),
    },
    {
      key: "insights",
      label: "数据洞察",
      children: <InsightCharts insights={insights} />,
    },
    ...(showMonitoring
      ? [
          {
            key: "changes",
            label: `变更历史${task.changes_detected ? ` (${task.changes_detected})` : ""}`,
            children: (
              <ChangeTrendChart
                changes={trackingChanges}
                stats={trackingStats}
                groupTasks={task.group_tasks || []}
              />
            ),
          },
        ]
      : []),
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>返回</Button>
        <Title level={3} style={{ margin: 0 }}>任务详情</Title>
        <Tag color={statusColors[getDisplayStatus(task, status)]}>{statusLabels[getDisplayStatus(task, status)]}</Tag>
        {connected && status === "running" && (
          <Tag color="green">实时连接</Tag>
        )}
      </Space>

      <Tabs items={tabItems} />
    </div>
  );
}
