/**
 * Up / down / flat indicator with optional delta value.
 */
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { Typography } from 'antd';

interface Props {
  value: number;
  /** Number of decimals to show on the percentage. */
  digits?: number;
}

export default function TrendArrow({ value, digits = 1 }: Props) {
  const epsilon = 0.0001;
  if (value > epsilon) {
    return (
      <Typography.Text type="success">
        <ArrowUpOutlined /> {(value * 100).toFixed(digits)}%
      </Typography.Text>
    );
  }
  if (value < -epsilon) {
    return (
      <Typography.Text type="danger">
        <ArrowDownOutlined /> {(Math.abs(value) * 100).toFixed(digits)}%
      </Typography.Text>
    );
  }
  return (
    <Typography.Text type="secondary">
      <MinusOutlined /> 0%
    </Typography.Text>
  );
}
