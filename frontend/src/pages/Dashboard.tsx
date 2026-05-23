import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Space, Spin, Typography, App } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import TaskCard from "../components/TaskCard";
import { api } from "../api/client";
import type { TaskSummary } from "../types";

const { Title } = Typography;

export default function Dashboard() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { message } = App.useApp();

  const fetchTasks = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listTasks();
      setTasks(data);
    } catch {
      message.error("获取任务列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    // 每 5 秒轮询
    const timer = setInterval(fetchTasks, 5000);
    return () => clearInterval(timer);
  }, [fetchTasks]);

  return (
    <div>
      {/* <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>爬虫任务</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchTasks}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/tasks/new")}>
            新建任务
          </Button>
        </Space>
      </Space> */}

      {loading && !tasks.length ? (
        <div style={{ textAlign: "center", marginTop: 80 }}>
          <Spin tip="加载中...">
            <div style={{ height: 40 }} />
          </Spin>
        </div>
      ) : !tasks.length ? (
        <div style={{ textAlign: "center", marginTop: 80, color: "#999" }}>
          暂无任务，点击"新建任务"开始
        </div>
      ) : (
        tasks.map((task) => (
          <TaskCard
            key={task.task_id}
            task={task}
            onClick={() => navigate(`/tasks/${task.task_id}`)}
          />
        ))
      )}
    </div>
  );
}
