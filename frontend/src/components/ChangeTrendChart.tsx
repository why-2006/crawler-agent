import ReactECharts from "echarts-for-react";
import type { ContentChange, GroupTask, TrackingStat } from "../types";
import { Card, Empty, Typography } from "antd";

const { Text } = Typography;

interface Props {
  changes: ContentChange[];
  stats: TrackingStat[];
  groupTasks: GroupTask[];
}

export default function ChangeTrendChart({ changes, stats, groupTasks }: Props) {
  const hasData = changes.length > 0 || stats.length > 0 || groupTasks.length > 0;
  if (!hasData) {
    return <Empty description="暂无变更数据，等待定时任务触发" />;
  }

  // 变更频率折线图：按任务时间展示变更数量
  const taskChangeMap: Record<string, number> = {};
  changes.forEach((c) => {
    const key = c.detected_at?.slice(0, 16) || "未知";
    taskChangeMap[key] = (taskChangeMap[key] || 0) + 1;
  });
  const freqCategories = Object.keys(taskChangeMap).sort();
  const freqValues = freqCategories.map((k) => taskChangeMap[k]);

  const freqOption = {
    title: { text: "变更频率趋势", left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "category", data: freqCategories, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: "value", name: "变更次数" },
    series: [{ name: "变更次数", type: "line", data: freqValues, smooth: true }],
  };

  // URL 变更热力图（Top 10）
  const topStats = stats.slice(0, 10);
  const heatOption = {
    title: { text: "URL 变更次数排行", left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: { type: "value", name: "变更次数" },
    yAxis: {
      type: "category",
      data: topStats.map((s) => (s.url.length > 50 ? s.url.slice(0, 50) + "..." : s.url)),
      inverse: true,
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        name: "变更次数",
        type: "bar",
        data: topStats.map((s, i) => ({
          value: s.change_count,
          itemStyle: {
            color: `hsl(${(i / topStats.length) * 60}, 70%, 50%)`,
          },
        })),
      },
    ],
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {changes.length > 0 && (
        <>
          <Card size="small">
            <ReactECharts option={freqOption} style={{ height: 300 }} />
          </Card>
          {topStats.length > 0 && (
            <Card size="small">
              <ReactECharts option={heatOption} style={{ height: 300 }} />
            </Card>
          )}
          <Card size="small" title="变更记录">
            {changes.slice(0, 20).map((c) => (
              <div key={c.id} style={{ marginBottom: 8, padding: "4px 0", borderBottom: "1px solid #f0f0f0" }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {c.detected_at?.slice(0, 19)}
                </Text>
                <br />
                <Text style={{ fontSize: 13 }}>{c.change_summary || "内容已更新"}</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {c.url}
                </Text>
              </div>
            ))}
            {changes.length > 20 && (
              <Text type="secondary">... 还有 {changes.length - 20} 条变更记录</Text>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
