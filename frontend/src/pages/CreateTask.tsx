import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Form, Input, InputNumber, Switch, Button, Card, Typography, App, Space, Select, Divider } from "antd";
import { ArrowLeftOutlined, ClockCircleOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import type { TaskCreateInput } from "../types";

const { Title, Text } = Typography;
const { TextArea } = Input;

const INTERVAL_OPTIONS = [
  { value: 30, label: "每 30 分钟" },
  { value: 60, label: "每小时" },
  { value: 360, label: "每 6 小时" },
  { value: 720, label: "每 12 小时" },
  { value: 1440, label: "每天" },
];

export default function CreateTask() {
  const [submitting, setSubmitting] = useState(false);
  const [monitoring, setMonitoring] = useState(false);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm<TaskCreateInput>();

  const onFinish = async (values: TaskCreateInput) => {
    setSubmitting(true);
    try {
      const payload = {
        ...values,
        recurring_interval_minutes: monitoring ? values.recurring_interval_minutes : 0,
      };
      const result = await api.createTask(payload);
      message.success(monitoring ? "定时监控任务创建成功" : "任务创建成功");
      navigate(`/tasks/${result.task_id}`);
    } catch {
      message.error("创建任务失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: "0 auto" }}>
      <Space style={{ marginBottom: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>返回</Button>
        <Title level={3} style={{ margin: 0 }}>新建爬取任务</Title>
      </Space>

      <Card>
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{
            max_depth: 3,
            max_pages: 50,
            use_javascript: false,
            recurring_interval_minutes: 60,
          }}
        >
          <Form.Item
            name="seed_url"
            label="种子 URL"
            rules={[
              { required: true, message: "请输入起始 URL" },
              { type: "url", message: "请输入有效的 URL" },
            ]}
          >
            <Input placeholder="https://example.com" />
          </Form.Item>

          <Form.Item
            name="data_description"
            label="数据描述"
            rules={[{ required: true, message: "请描述要提取的数据" }]}
          >
            <TextArea
              rows={3}
              placeholder="例如：商品名称、价格、描述、SKU"
            />
          </Form.Item>

          <Form.Item name="max_depth" label="最大深度">
            <InputNumber min={1} max={20} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item name="max_pages" label="最大页数">
            <InputNumber min={1} max={500} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item name="use_javascript" label="JS 渲染" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Divider />
          <Space align="center" style={{ marginBottom: 8 }}>
            <ClockCircleOutlined />
            <Text strong>增量监控（可选）</Text>
          </Space>
          <Form.Item label="启用定时监控" style={{ marginBottom: 8 }}>
            <Switch checked={monitoring} onChange={setMonitoring} />
          </Form.Item>
          {monitoring && (
            <Form.Item name="recurring_interval_minutes" label="监控间隔">
              <Select options={INTERVAL_OPTIONS} />
            </Form.Item>
          )}
          <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
            开启后系统会定时爬取并追踪页面内容变化
          </Text>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              创建任务
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
