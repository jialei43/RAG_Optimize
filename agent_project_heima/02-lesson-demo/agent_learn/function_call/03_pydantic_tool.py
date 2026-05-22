"""
模式三：Pydantic 模式
用 Pydantic BaseModel 定义工具参数结构，结合 StructuredTool 封装。
适合：参数复杂、需要数据验证、类型约束严格的生产场景。

Pydantic 模式的核心优势：
  - Field(description=...) 精确描述每个字段
  - Field(ge=1, le=10) 等约束条件自动校验参数
  - Optional / Union 等复杂类型完美支持
  - 业务逻辑与参数定义完全分离，结构清晰
"""

import os  # 环境变量
from typing import Optional, List  # 类型注解
from dotenv import load_dotenv, find_dotenv  # 自动查找 .env
# pie-dan-tick / paɪˈdæntɪk  派-丹-提克
from pydantic import BaseModel, Field, field_validator  # Pydantic 核心组件
from langchain_openai import ChatOpenAI  # OpenAI 协议客户端
# StructuredTool 斯垂克彻德-图
from langchain_core.tools import StructuredTool  # 结构化工具包装器
from langchain_core.messages import HumanMessage, ToolMessage  # 消息类型

load_dotenv(find_dotenv())  # 加载 .env 文件


# ── 初始化 Qwen 模型 ────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="qwen-plus",  # Qwen Plus 模型
    api_key=os.getenv("DASHSCOPE_API_KEY"),  # 从环境变量读取 Key
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # DashScope 兼容端点
)


# ── Step 1：用 Pydantic BaseModel 定义参数结构 ───────────────────────────────
# 规则：
#   - 类名随意，建议以 Input 结尾，表示这是工具的输入参数模型
#   - 每个字段用 Field(description=...) 描述，模型靠这个理解如何填参数
#   - 可以加验证器 @field_validator 做数据校验


class WeatherInput(BaseModel):
    """天气查询工具的参数模型"""

    city: str = Field(description="城市名称，例如：北京、上海、广州")  # 必填，无默认值
    unit: Optional[str] = Field(  # Optional 表示可选参数
        default="celsius",  # 默认值摄氏
        description="温度单位：celsius（摄氏度）或 fahrenheit（华氏度）",
    )

    @field_validator("unit")  # 验证器，自动在赋值时执行
    @classmethod
    def validate_unit(cls, v: str) -> str:
        """确保 unit 只能是合法值，防止模型传入非预期内容"""
        allowed = {"celsius", "fahrenheit"}  # 允许的值集合
        if v not in allowed:
            raise ValueError(f"unit 必须是 {allowed} 之一，收到: {v}")  # 非法值时抛出异常
        return v  # 合法则原样返回


class FlightSearchInput(BaseModel):
    """机票查询工具的参数模型，演示复杂参数结构"""

    origin: str = Field(description="出发城市或机场代码，例如：北京 或 PEK")  # 出发地
    destination: str = Field(description="目的城市或机场代码，例如：上海 或 SHA")  # 目的地
    date: str = Field(description="出发日期，格式 YYYY-MM-DD，例如：2026-06-01")  # 日期
    passengers: int = Field(  # 整数类型，带范围约束
        default=1,
        ge=1,  # ge = greater than or equal，最少 1 人
        le=9,  # le = less than or equal，最多 9 人（航空公司限制）
        description="乘客人数，1-9 之间",
    )
    cabin_class: Optional[str] = Field(  # 可选的舱位等级
        default="economy",
        description="舱位等级：economy（经济舱）、business（商务舱）、first（头等舱）",
    )

    @field_validator("date")  # 验证日期格式
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """检查日期格式是否为 YYYY-MM-DD"""
        from datetime import datetime  # 延迟导入，只在验证时用
        try:
            datetime.strptime(v, "%Y-%m-%d")  # 尝试解析日期
        except ValueError:
            raise ValueError(f"日期格式错误，应为 YYYY-MM-DD，收到: {v}")  # 格式不对时报错
        return v  # 合法则返回原始字符串


class RestaurantSearchInput(BaseModel):
    """餐厅搜索工具的参数模型，演示列表类型参数"""

    city: str = Field(description="搜索城市")  # 城市
    cuisine_types: Optional[List[str]] = Field(  # List[str] 表示字符串列表
        default=None,
        description="菜系偏好列表，例如：['川菜', '粤菜']，不填则不限制菜系",
    )
    max_price_per_person: Optional[int] = Field(  # 人均价格上限
        default=None,
        ge=0,  # 不能为负数
        description="人均价格上限（元），不填则不限制价格",
    )
    min_rating: float = Field(  # 最低评分
        default=4.0,
        ge=0.0,  # 评分最低 0
        le=5.0,  # 评分最高 5
        description="最低评分（0-5），默认 4.0",
    )


# ── Step 2：实现工具的真实业务逻辑函数 ──────────────────────────────────────

def get_weather_func(city: str, unit: str = "celsius") -> dict:
    """天气查询逻辑（函数参数和 WeatherInput 字段一一对应）"""
    mock_data = {  # 模拟天气数据
        "北京": {"temp": 28, "desc": "晴", "wind": "东南风3级", "humidity": "40%"},
        "上海": {"temp": 32, "desc": "多云", "wind": "南风2级", "humidity": "75%"},
        "广州": {"temp": 35, "desc": "雷阵雨", "wind": "西南风4级", "humidity": "85%"},
    }
    data = mock_data.get(city, {"temp": 0, "desc": "暂无数据", "wind": "无", "humidity": "0%"})  # 默认值
    unit_label = "°C" if unit == "celsius" else "°F"  # 单位符号
    return {**data, "city": city, "unit": unit_label}  # 合并返回


def search_flights_func(
    origin: str,
    destination: str,
    date: str,
    passengers: int = 1,
    cabin_class: str = "economy",
) -> dict:
    """机票搜索逻辑（模拟数据）"""
    # 模拟价格计算：商务舱是经济舱的 3 倍，头等舱是 5 倍
    base_price = {"economy": 800, "business": 2400, "first": 4000}
    price_per_person = base_price.get(cabin_class, 800)  # 获取单人价格
    total = price_per_person * passengers  # 计算总价
    return {  # 返回模拟的搜索结果
        "route": f"{origin} → {destination}",
        "date": date,
        "passengers": passengers,
        "cabin_class": cabin_class,
        "price_per_person": f"¥{price_per_person}",
        "total_price": f"¥{total}",
        "available_flights": ["CA1234 08:00", "MU5678 14:30", "CZ9012 19:15"],  # 模拟航班列表
    }


def search_restaurants_func(
    city: str,
    cuisine_types: Optional[List[str]] = None,
    max_price_per_person: Optional[int] = None,
    min_rating: float = 4.0,
) -> dict:
    """餐厅搜索逻辑（模拟数据）"""
    # 模拟餐厅数据库
    all_restaurants = [
        {"name": "老北京涮肉", "cuisine": "北京菜", "rating": 4.8, "price": 120, "city": "北京"},
        {"name": "外婆家", "cuisine": "杭帮菜", "rating": 4.5, "price": 80, "city": "上海"},
        {"name": "蜀大侠火锅", "cuisine": "川菜", "rating": 4.6, "price": 100, "city": "北京"},
        {"name": "大董烤鸭", "cuisine": "北京菜", "rating": 4.9, "price": 350, "city": "北京"},
    ]
    results = [r for r in all_restaurants if r["city"] == city]  # 按城市过滤
    if cuisine_types:  # 如果指定了菜系，进一步过滤
        results = [r for r in results if r["cuisine"] in cuisine_types]
    if max_price_per_person is not None:  # 如果指定了价格上限，进一步过滤
        results = [r for r in results if r["price"] <= max_price_per_person]
    results = [r for r in results if r["rating"] >= min_rating]  # 按最低评分过滤
    return {"city": city, "found": len(results), "restaurants": results}  # 返回搜索结果


# ── Step 3：用 StructuredTool 把函数和 Schema 绑定在一起 ─────────────────────

weather_tool = StructuredTool.from_function(
    func=get_weather_func,  # 业务逻辑函数
    name="get_weather",  # 工具名（模型调用时使用的名字）
    description="获取指定城市的当前天气信息，包括气温、天气状况、风力和湿度",  # 工具描述
    args_schema=WeatherInput,  # 绑定 Pydantic Schema，自动生成参数描述和校验
)

flight_tool = StructuredTool.from_function(
    func=search_flights_func,  # 机票查询函数
    name="search_flights",  # 工具名
    description="搜索指定路线和日期的机票信息，返回可用航班和价格",  # 描述
    args_schema=FlightSearchInput,  # 复杂参数的 Pydantic Schema
)

restaurant_tool = StructuredTool.from_function(
    func=search_restaurants_func,  # 餐厅搜索函数
    name="search_restaurants",  # 工具名
    description="在指定城市搜索餐厅，支持按菜系、价格、评分筛选",  # 描述
    args_schema=RestaurantSearchInput,  # 含 List 参数的复杂 Schema
)

tools = [weather_tool, flight_tool, restaurant_tool]  # 所有工具列表
llm_with_tools = llm.bind_tools(tools)  # 把工具列表绑定到模型
TOOL_MAP = {t.name: t for t in tools}  # 构建名称到工具对象的映射


# ── 查看 Pydantic 生成的 Schema ────────────────────────────────────────────

def inspect_schemas() -> None:
    """打印三个工具的 Pydantic Schema，对比不同复杂度的参数定义"""
    import json  # 格式化输出用
    print("\n【Pydantic Schema 对比】")
    for t in tools:
        print(f"\n--- {t.name} ---")
        schema = t.args_schema.model_json_schema()  # 获取 JSON Schema
        print(json.dumps(schema, indent=2, ensure_ascii=False))  # 格式化打印


# ── 通用 Agent 执行器 ──────────────────────────────────────────────────────

def run_agent(question: str, max_rounds: int = 5) -> None:
    """完整的 Agent 执行流程，支持多轮工具调用"""
    print(f"\n{'='*50}")
    print(f"用户提问: {question}")
    print("=" * 50)

    messages = [HumanMessage(content=question)]  # 初始消息

    for round_num in range(max_rounds):  # 限制最大轮次，防止无限循环
        response = llm_with_tools.invoke(messages)  # 调用模型
        messages.append(response)  # 记录模型回复

        if not response.tool_calls:  # 无工具调用，直接返回最终答案
            print(f"\n最终回复: {response.content}")
            return

        print(f"\n[第{round_num + 1}轮工具调用]")

        for tc in response.tool_calls:  # 逐个执行工具
            tool_obj = TOOL_MAP.get(tc["name"])  # 找工具对象
            try:
                result = tool_obj.invoke(tc["args"])  # 执行工具（Pydantic 会自动校验参数）
            except Exception as e:
                result = {"error": str(e)}  # 参数校验失败时捕获异常

            print(f"  {tc['name']}({tc['args']})")
            print(f"  结果: {result}")

            messages.append(  # 工具结果加入历史
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    print("[达到最大轮次]")  # 兜底提示


# ── 演示 Pydantic 参数校验能力 ────────────────────────────────────────────

def demo_pydantic_validation() -> None:
    """直接用 Pydantic 模型演示参数校验，不走模型调用"""
    print("\n\n【Pydantic 参数校验演示】")

    # 合法参数 - 正常创建
    valid = WeatherInput(city="北京", unit="celsius")  # 合法参数
    print(f"合法参数: {valid.model_dump()}")  # model_dump() 转换成字典

    # 非法 unit - 触发验证器
    try:
        invalid = WeatherInput(city="北京", unit="kelvin")  # 非法的温度单位
        print(f"非法参数通过了？{invalid}")  # 不应该到这里
    except Exception as e:
        print(f"校验失败（预期）: {e}")  # 期望的错误

    # 非法乘客数 - 超出范围
    try:
        invalid_flight = FlightSearchInput(  # 乘客数超出上限 9
            origin="北京", destination="上海", date="2026-06-01", passengers=15
        )
        print(f"非法乘客数通过了？{invalid_flight}")
    except Exception as e:
        print(f"乘客数校验失败（预期）: {e}")  # 期望的错误

    # 非法日期格式 - 触发日期验证器
    try:
        invalid_date = FlightSearchInput(  # 日期格式错误
            origin="北京", destination="上海", date="2026/06/01"  # 应该是 - 分隔
        )
        print(f"非法日期通过了？{invalid_date}")
    except Exception as e:
        print(f"日期校验失败（预期）: {e}")  # 期望的错误


# ── 运行演示 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_pydantic_validation()  # 先演示参数校验

    inspect_schemas()  # 查看生成的 Schema 结构

    print("\n\n【演示一：天气查询】")
    run_agent("广州今天天气怎么样？")

    print("\n\n【演示二：机票查询（复杂参数）】")
    run_agent("帮我查一下明天（2026-05-23）从北京飞上海的商务舱机票，2个人")

    print("\n\n【演示三：餐厅搜索（含列表参数）】")
    run_agent("帮我在北京找几家评分 4.5 以上、人均 200 元以下的北京菜餐厅")
