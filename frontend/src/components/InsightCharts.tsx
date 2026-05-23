import ReactECharts from "echarts-for-react";
import type { DataInsight } from "../types";
import { Card, Empty, Typography } from "antd";

const { Text } = Typography;

interface Props {
  insights: DataInsight[];
}

export default function InsightCharts({ insights }: Props) {
  if (!insights || insights.length === 0) {
    return <Empty description="暂无数据洞察" />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {insights.map((insight, idx) => {
        const { categories, series } = insight.data;
        const option = {
          title: { text: insight.title, left: "center", textStyle: { fontSize: 14 } },
          tooltip: { trigger: insight.chart_type === "pie" ? "item" : "axis" },
          legend: {
            bottom: 0,
            data: series.map((s) => s.name),
          },
          grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
          xAxis:
            insight.chart_type !== "pie"
              ? { type: "category", data: categories, axisLabel: { rotate: 30 } }
              : undefined,
          yAxis: insight.chart_type !== "pie" ? { type: "value" } : undefined,
          series: series.map((s) => ({
            name: s.name,
            type: insight.chart_type,
            data: insight.chart_type === "pie"
              ? categories.map((c, i) => ({ name: c, value: s.values[i] }))
              : s.values,
            radius: insight.chart_type === "pie" ? ["40%", "70%"] : undefined,
          })),
        };

        return (
          <Card key={idx} size="small">
            <ReactECharts option={option} style={{ height: 300 }} />
            <Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 4 }}>
              {insight.description}
            </Text>
          </Card>
        );
      })}
    </div>
  );
}
