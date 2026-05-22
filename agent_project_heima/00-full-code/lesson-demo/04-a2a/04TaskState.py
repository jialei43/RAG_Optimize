"""
需求：定义任务状态枚举，管理任务生命周期
思路步骤：
1. 导入任务状态枚举类
2. 验证任务状态值的正确性
3. 展示不同任务状态的值和表示
"""

from python_a2a import TaskState  # 只需相关导入
# 检查任务状态
if TaskState.COMPLETED == "completed":
    print("任务完成")
state = TaskState.SUBMITTED
print("转换后的状态值：", state.value)
print(state)

# 任务完成
# 转换后的状态值： submitted
# TaskState.SUBMITTED