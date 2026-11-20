"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    """状态动作使用独立契约，避免与登记的 values 载荷混用。"""

    action: str
    remark: str | None = None


class SchedulePlanPayload(BaseModel):
    """生成合并排程时选择冲突处置口径：优先补数或优先合并。"""

    resolution: str = "优先补数"



class TopicRegistryEntry(BaseModel):
    """数据主题明细结构。"""

    field_0: str | None = None  # 主题编号
    field_1: str | None = None  # 主题名称
    field_2: str | None = None  # 消息格式
    field_3: str | None = None  # 序列化协议
    field_4: str | None = None  # 分区键列
    field_5: str | None = None  # 保留时长
    field_6: str | None = None  # 压缩类型
    field_7: str | None = None  # Schema版本

class FlinkJobEntry(BaseModel):
    """流式任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 消费主题
    field_2: str | None = None  # 转换逻辑
    field_3: str | None = None  # 输出表名
    field_4: str | None = None  # 并行度
    field_5: str | None = None  # 检查点间隔
    field_6: str | None = None  # 状态后端
    field_7: str | None = None  # 水位策略

class KafkaConnectorEntry(BaseModel):
    """接入配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 集群地址
    field_2: str | None = None  # 消费组名
    field_3: str | None = None  # 偏移策略
    field_4: str | None = None  # 反序列化器
    field_5: str | None = None  # 批量大小
    field_6: str | None = None  # 超时时间
    field_7: str | None = None  # 死信队列

class SchemaEvolveEntry(BaseModel):
    """演进规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 关联主题
    field_2: str | None = None  # 新增字段
    field_3: str | None = None  # 删除字段
    field_4: str | None = None  # 类型变更
    field_5: str | None = None  # 默认值填充
    field_6: str | None = None  # 兼容模式
    field_7: str | None = None  # 生效版本

class UpsertMergeEntry(BaseModel):
    """合并策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标表名
    field_2: str | None = None  # 合并键列
    field_3: str | None = None  # 插入列
    field_4: str | None = None  # 更新列
    field_5: str | None = None  # 删除标记
    field_6: str | None = None  # 排序字段
    field_7: str | None = None  # 合并引擎

class LakePartitionEntry(BaseModel):
    """分区定义明细结构。"""

    field_0: str | None = None  # 分区编号
    field_1: str | None = None  # 目标表名
    field_2: str | None = None  # 分区列名
    field_3: str | None = None  # 分区粒度
    field_4: str | None = None  # 分区转换
    field_5: str | None = None  # 存储位置
    field_6: str | None = None  # 文件格式
    field_7: str | None = None  # 生命周期

class StreamQualityEntry(BaseModel):
    """质量规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 监控主题
    field_2: str | None = None  # 校验类型
    field_3: str | None = None  # 告警阈值
    field_4: str | None = None  # 采样比例
    field_5: str | None = None  # 检测窗口
    field_6: str | None = None  # 阻断动作
    field_7: str | None = None  # 规则版本

class IcebergTableEntry(BaseModel):
    """表元数据明细结构。"""

    field_0: str | None = None  # 表编号
    field_1: str | None = None  # 表名称
    field_2: str | None = None  # 存储格式
    field_3: str | None = None  # 分区策略
    field_4: str | None = None  # 排序字段
    field_5: str | None = None  # 快照过期
    field_6: str | None = None  # 孤立文件清理
    field_7: str | None = None  # 元数据版本

class WatermarkTrackEntry(BaseModel):
    """水位标记明细结构。"""

    field_0: str | None = None  # 标记编号
    field_1: str | None = None  # 数据主题
    field_2: str | None = None  # 分区编号
    field_3: str | None = None  # 事件时间水位
    field_4: str | None = None  # 处理时间水位
    field_5: str | None = None  # 延迟记录数
    field_6: str | None = None  # 消费偏移
    field_7: str | None = None  # 检查时间

class DeadLetterEntry(BaseModel):
    """死信记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 原始主题
    field_2: str | None = None  # 原始分区
    field_3: str | None = None  # 失败原因
    field_4: str | None = None  # 原始消息体
    field_5: str | None = None  # 重试次数
    field_6: str | None = None  # 入库时间
    field_7: str | None = None  # 处置状态

class MaterializedViewEntry(BaseModel):
    """物化视图明细结构。"""

    field_0: str | None = None  # 视图编号
    field_1: str | None = None  # 查询SQL
    field_2: str | None = None  # 基表名
    field_3: str | None = None  # 刷新模式
    field_4: str | None = None  # 刷新间隔
    field_5: str | None = None  # 存储位置
    field_6: str | None = None  # 数据量
    field_7: str | None = None  # 最后刷新

class ChangeCaptureEntry(BaseModel):
    """CDC配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 源数据库
    field_2: str | None = None  # 源表名
    field_3: str | None = None  # 快照模式
    field_4: str | None = None  # 捕获列
    field_5: str | None = None  # 变更序号
    field_6: str | None = None  # 增量阶段
    field_7: str | None = None  # 目标主题

class CompactPolicyEntry(BaseModel):
    """清理策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标表名
    field_2: str | None = None  # 触发条件
    field_3: str | None = None  # 合并并发
    field_4: str | None = None  # 目标文件大小
    field_5: str | None = None  # 最小文件数
    field_6: str | None = None  # 保留快照数
    field_7: str | None = None  # 执行时间窗口

class StreamLineageEntry(BaseModel):
    """血缘记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 上游主题
    field_2: str | None = None  # 下游表名
    field_3: str | None = None  # 转换节点
    field_4: str | None = None  # 字段映射
    field_5: str | None = None  # 采集时间
    field_6: str | None = None  # 延迟偏移
    field_7: str | None = None  # 链路版本

class BackfillStreamEntry(BaseModel):
    """补数任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 目标表名
    field_2: str | None = None  # 起始偏移
    field_3: str | None = None  # 截止偏移
    field_4: str | None = None  # 重放速率
    field_5: str | None = None  # 并行度
    field_6: str | None = None  # 覆盖策略
    field_7: str | None = None  # 结果校验

class SinkDispatchEntry(BaseModel):
    """分发规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 湖表名
    field_2: str | None = None  # 目标系统
    field_3: str | None = None  # 写入模式
    field_4: str | None = None  # 字段映射
    field_5: str | None = None  # 过滤条件
    field_6: str | None = None  # 批次大小
    field_7: str | None = None  # 失败回退

class TtlPolicyEntry(BaseModel):
    """生命周期明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标表名
    field_2: str | None = None  # 热数据保留
    field_3: str | None = None  # 温数据窗口
    field_4: str | None = None  # 冷归档策略
    field_5: str | None = None  # 过期动作
    field_6: str | None = None  # 分区粒度
    field_7: str | None = None  # 恢复超时

class RealtimeMetricsEntry(BaseModel):
    """指标定义明细结构。"""

    field_0: str | None = None  # 指标编号
    field_1: str | None = None  # 指标名称
    field_2: str | None = None  # 聚合窗口
    field_3: str | None = None  # 聚合函数
    field_4: str | None = None  # 过滤条件
    field_5: str | None = None  # 分组维度
    field_6: str | None = None  # 输出表名
    field_7: str | None = None  # 指标版本
