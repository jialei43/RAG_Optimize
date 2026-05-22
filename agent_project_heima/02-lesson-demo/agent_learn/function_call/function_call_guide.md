# Function Call（工具调用）学习指南

> 适合人群：AI 应用开发初学者，了解 Python 基础，第一次接触 LLM 工具调用。

---

## 一、什么是 Function Call？

**Function Call（函数调用 / 工具调用）** 是让大模型能够主动调用外部函数的一种机制。

普通对话中，模型只能返回文字。有了 Function Call，模型可以：

```
用户：现在北京的天气怎么样？

模型（内部）：我需要调用 get_weather("北京") 这个函数来获取数据
         ↓
外部函数执行：返回 {"city": "北京", "temp": "28°C", "desc": "晴"}
         ↓
模型（最终回复）：北京现在天气晴朗，气温 28°C，适合出行。
```

**核心价值：打破模型知识边界，连接真实世界。**

---

## 二、Function Call 的完整流程

```
┌─────────────────────────────────────────────────────┐
│                   完整调用流程                        │
│                                                     │
│  ① 用户发送消息                                      │
│       ↓                                             │
│  ② 开发者把「工具定义」一起发给模型                    │
│       ↓                                             │
│  ③ 模型判断是否需要调用工具                            │
│       ↓ (需要)          ↓ (不需要)                   │
│  ④ 模型返回工具名+参数   直接返回文字答案               │
│       ↓                                             │
│  ⑤ 开发者代码执行函数，得到结果                        │
│       ↓                                             │
│  ⑥ 把结果再发给模型                                   │
│       ↓                                             │
│  ⑦ 模型根据结果生成最终回复                            │
└─────────────────────────────────────────────────────┘
```

---

## 三、快速上手：用 Claude API 实现 Function Call

### 3.1 安装依赖

```bash
pip install anthropic
```

### 3.2 定义工具

工具定义是一个字典，告诉模型这个工具叫什么、有什么用、需要哪些参数。

```python
# 工具定义：获取天气
tools = [
    {
        "name": "get_weather",                          # 工具名称
        "description": "获取指定城市的当前天气信息",       # 描述（模型靠这个决定要不要调用）
        "input_schema": {                               # 参数的 JSON Schema
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，例如：北京、上海"
                }
            },
            "required": ["city"]                        # 必填参数
        }
    }
]
```

### 3.3 实现真正的函数逻辑

```python
import json

def get_weather(city: str) -> dict:
    """真实场景中这里会调用天气 API，这里用假数据演示"""
    mock_data = {
        "北京": {"temp": "28°C", "desc": "晴", "humidity": "40%"},
        "上海": {"temp": "32°C", "desc": "多云", "humidity": "75%"},
        "广州": {"temp": "35°C", "desc": "雷阵雨", "humidity": "85%"},
    }
    return mock_data.get(city, {"temp": "未知", "desc": "暂无数据", "humidity": "未知"})
```

### 3.4 完整代码示例

```python
import anthropic
import json

client = anthropic.Anthropic()  # 默认读取环境变量 ANTHROPIC_API_KEY

# ① 工具定义
tools = [
    {
        "name": "get_weather",
        "description": "获取指定城市的当前天气信息",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称"
                }
            },
            "required": ["city"]
        }
    }
]

# ② 模拟真实函数
def get_weather(city: str) -> dict:
    mock_data = {
        "北京": {"temp": "28°C", "desc": "晴"},
        "上海": {"temp": "32°C", "desc": "多云"},
    }
    return mock_data.get(city, {"temp": "未知", "desc": "暂无数据"})

# ③ 第一轮：把用户问题 + 工具定义发给模型
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[
        {"role": "user", "content": "北京今天天气怎么样？"}
    ]
)

print(f"停止原因: {response.stop_reason}")  # 期望看到 tool_use

# ④ 判断模型是否要调用工具
if response.stop_reason == "tool_use":
    # 从返回内容中找到 tool_use 块
    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    
    tool_name = tool_use_block.name          # 工具名
    tool_input = tool_use_block.input        # 工具参数（dict）
    tool_use_id = tool_use_block.id          # 本次调用的唯一 ID
    
    print(f"模型要调用: {tool_name}({tool_input})")
    
    # ⑤ 在本地执行函数
    result = get_weather(**tool_input)
    print(f"函数返回结果: {result}")
    
    # ⑥ 第二轮：把工具结果返回给模型
    final_response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=tools,
        messages=[
            {"role": "user", "content": "北京今天天气怎么样？"},
            {"role": "assistant", "content": response.content},   # 模型第一轮的回复
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,               # 对应上面的 ID
                        "content": json.dumps(result, ensure_ascii=False)
                    }
                ]
            }
        ]
    )
    
    # ⑦ 输出最终答案
    print(f"\n最终回复: {final_response.content[0].text}")
```

**预期输出：**
```
停止原因: tool_use
模型要调用: get_weather({'city': '北京'})
函数返回结果: {'temp': '28°C', 'desc': '晴'}

最终回复: 北京今天天气晴朗，气温 28°C，非常适合外出活动！
```

---

## 四、定义多个工具

一次可以给模型提供多个工具，模型会自己选择合适的工具调用。

```python
tools = [
    {
        "name": "get_weather",
        "description": "获取城市天气",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "calculate",
        "description": "执行数学计算，支持加减乘除",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如：2 + 3 * 4"
                }
            },
            "required": ["expression"]
        }
    },
    {
        "name": "search_web",
        "description": "搜索网络上的信息",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    }
]
```

---

## 五、工具调度器：自动处理任意工具

上面的代码写死了函数名，实际开发中用「调度器」模式，自动分发：

```python
import anthropic
import json

client = anthropic.Anthropic()

# 所有可用工具的实现放在这个字典里，键是工具名
TOOL_IMPLEMENTATIONS = {
    "get_weather": lambda city: {"temp": "28°C", "desc": "晴"},
    "calculate": lambda expression: {"result": eval(expression)},   # 注意：生产环境不要用 eval
}

def run_with_tools(user_message: str, tools: list) -> str:
    """通用工具调用执行器"""
    messages = [{"role": "user", "content": user_message}]
    
    while True:  # 循环处理，直到模型不再调用工具
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=tools,
            messages=messages
        )
        
        if response.stop_reason != "tool_use":
            # 模型不再调用工具，返回最终文字回复
            return response.content[0].text
        
        # 把模型的回复加入消息历史
        messages.append({"role": "assistant", "content": response.content})
        
        # 处理所有工具调用（一次回复里可能包含多个工具调用）
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue  # 跳过非工具调用的块
            
            # 调用对应的函数
            func = TOOL_IMPLEMENTATIONS.get(block.name)
            if func:
                result = func(**block.input)
            else:
                result = {"error": f"未找到工具: {block.name}"}
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False)
            })
        
        # 把工具结果追加到消息历史
        messages.append({"role": "user", "content": tool_results})


# 使用示例
answer = run_with_tools("北京今天天气怎么样？", tools=[...])  # 传入工具定义
print(answer)
```

---

## 六、关键概念速查

| 概念 | 说明 |
|------|------|
| `tools` | 工具定义列表，每个工具包含 name / description / input_schema |
| `stop_reason` | 模型停止的原因：`end_turn`（正常结束）/ `tool_use`（需要调用工具） |
| `tool_use` block | 模型返回的工具调用块，包含 id / name / input |
| `tool_result` | 开发者把函数执行结果返回给模型时用的消息类型 |
| `tool_use_id` | 每次工具调用的唯一 ID，tool_result 必须带上对应的 ID |
| `input_schema` | JSON Schema 格式，描述工具参数的类型和约束 |

---

## 七、常见错误 & 解决方法

### 错误 1：模型没有调用工具，直接回答了
**原因**：工具描述不够清晰，模型不知道该用这个工具。  
**解决**：完善 `description` 字段，明确说明工具的适用场景和能力。

### 错误 2：`tool_use_id` 对不上
**原因**：返回 tool_result 时没有用模型返回的那个 id。  
**解决**：务必从 `tool_use_block.id` 取 id，不要自己生成。

### 错误 3：参数类型错误
**原因**：`input_schema` 中定义了 `integer`，但传入了字符串。  
**解决**：在 input_schema 里严格定义类型，或者在函数里做类型转换。

### 错误 4：一直循环调用工具
**原因**：工具返回了错误信息，但模型反复尝试。  
**解决**：在循环里加最大迭代次数限制（建议最多 10 次）。

---

## 八、进阶：工具调用控制

Claude API 支持通过 `tool_choice` 控制工具调用行为：

```python
# 让模型自己决定（默认）
tool_choice = {"type": "auto"}

# 强制模型必须调用某个工具
tool_choice = {"type": "tool", "name": "get_weather"}

# 禁止调用任何工具，只返回文字
tool_choice = {"type": "none"}

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    tool_choice=tool_choice,    # 传入控制参数
    messages=[...]
)
```

---

## 九、完整练习项目建议

学完本文档后，可以动手做以下练习：

1. **天气查询机器人**：接入真实天气 API（如 OpenWeatherMap），实现城市天气查询。
2. **计算器助手**：定义加减乘除四个工具，让模型选择调用。
3. **文件操作助手**：定义读文件、写文件工具，通过自然语言操作本地文件。
4. **Agent 雏形**：组合多个工具 + 循环调用，让模型自主完成多步骤任务。

---

## 十、参考资料

- [Anthropic 官方文档 - Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Claude API Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [JSON Schema 规范](https://json-schema.org/understanding-json-schema/)
