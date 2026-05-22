"""
需求：定义任务状态详情，跟踪任务执行情况
思路步骤：
1. 创建不同状态的任务状态对象（完成、失败等）
2. 为每种状态设置相应的消息说明
3. 输出状态对象的字典表示用于调试和序列化
"""

from python_a2a import TaskStatus, TaskState

status_completed = TaskStatus(
    state=TaskState.COMPLETED,
    message={"info": "任务成功完成"}
)

status_failed = TaskStatus(
    state=TaskState.FAILED,
    message={"error": "无法处理请求"}
)

# 打印字典表示
print("完成状态：", status_completed.to_dict())
print("失败状态：", status_failed.to_dict())
# 完成状态： {'state': 'completed', 'timestamp': '2026-03-02T09:40:07.032889', 'message': {'info': '任务成功完成'}}
# 失败状态： {'state': 'failed', 'timestamp': '2026-03-02T09:40:07.032889', 'message': {'error': '无法处理请求'}}
