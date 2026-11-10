# Day 10｜LangChain + MCP

> 本文件 = 原 Day 10 中 MCP / Tool Schema 部分的全部内容（保留）+ 补充的 LangChain 基础、Tool Calling、MCP 会话机制与完整调用链。
> 原 Day 10 里的 Checkpointer、状态持久化两节已经并入 `09-langgraph.md`（第 11、12 节），内容没有删减。
> 标注「**补充**」的部分是新增内容。
> 你没有提供 `news_mcp.py` 和 `llm_client.py`，所以涉及这两个文件内部实现的地方，我只能按代码调用方式推断，并会标明「需对照源码确认」。

## 技术面试回答结构

1. 定义：它是什么？用自己的话解释概念
2. 目的：为什么需要它？理解它解决什么问题
3. 原理：它内部怎么工作？理解核心机制
4. 实践：我在项目中怎么使用？
5. 取舍：有什么局限，为什么选择它？

---

## 零、先看全局：技术栈分层

```text
┌──────────────────────────────────────────────────────────┐
│ 应用层   FastAPI / main()：接收用户问题，调用 app.ainvoke    │
├──────────────────────────────────────────────────────────┤
│ 编排层   LangGraph：StateGraph、条件路由、ToolNode、           │
│          Checkpointer（Day 9）                              │
├──────────────────────────────────────────────────────────┤
│ 组件层   LangChain：ChatModel、Message、@tool、               │
│          bind_tools、trim_messages                          │
├──────────────────────────────────────────────────────────┤
│ 协议层   MCP：langchain-mcp-adapters（Client）⇄ MCP Server    │
├──────────────────────────────────────────────────────────┤
│ 业务层   news_mcp.py → 新闻检索 / 日报读取；                   │
│          pipeline.daily_flow → 日报生成                      │
└──────────────────────────────────────────────────────────┘
```

两条工具来源（要分清）：

```text
search_news / get_daily_report / search_news_semantic
    └─ 来自 MCP Server（独立子进程，通过 MCP 协议调用）

request_daily_report
    └─ 本地 @tool（和 Agent 同一个进程，直接 Python 调用）
```

两者最终都变成 LangChain 的 Tool 对象，放进同一个 `TOOLS` 列表，对 LangGraph 来说没有区别。

---

## 一、学习内容与记录

### 1. LangChain 和 LangGraph 的关系（补充）

**定义：**

- LangChain：LLM 应用的**组件库**，提供统一的**模型接口、消息类型、工具定义、提示模板、输出解析**等。
- LangGraph：LLM 应用的**编排运行时**，用图来描述有状态、可循环的流程。

**目的：**

LangChain 解决「怎么用统一的方式调用各种模型和工具」；LangGraph 解决「**多步骤、带循环和状态**的流程怎么编排与持久化」。

**原理：**

```text
LangChain（零件）                    LangGraph（组装与运行）
  ChatModel      ───────────▶   agent 节点里调用
  Message 类型   ───────────▶   State 里保存（MessagesState）
  @tool / Tool   ───────────▶   ToolNode 执行
  trim_messages  ───────────▶   agent 节点里裁剪历史
```

依赖关系：LangGraph 可以脱离 LangChain 单独使用，但在 Agent 场景下通常直接复用 `langchain_core` 里的消息和工具类型。你的代码里就同时用了：

| 来自 | 用到的东西 |
|---|---|
| `langchain_core` | `SystemMessage`、`HumanMessage`、`AIMessage`、`ToolMessage`、`trim_messages`、`@tool` |
| `langgraph` | `StateGraph`、`MessagesState`、`ToolNode`、`Send`、`AsyncSqliteSaver` |
| `langchain_mcp_adapters` | `MultiServerMCPClient`、`load_mcp_tools` |

**实践：**

新版本的 LangChain 提供了现成的 Agent 构造函数（底层基于 LangGraph，具体名称和用法以所装版本文档为准）。你的项目选择自己用 `StateGraph` 搭图，是因为需要自定义：工具分组并行、超时、上下文裁剪等，现成封装不方便做到。

**局限与取舍：**

- 现成 Agent 封装上手快，但定制空间小。
- 自己搭图控制力强，但要自己处理循环保护、异常等细节。

---

### 2. ChatModel、Message、Tool 的作用（补充）

**定义：**

- ChatModel：LangChain 对各家聊天模型的统一封装。
- Message：对话中的消息对象（System / Human / AI / Tool）。
- Tool：模型可以请求调用的外部能力。

**目的：**

屏蔽不同厂商 API 的差异（消息格式、工具格式、返回格式都不一样），让上层代码只面向统一接口编程。

**原理：**

**ChatModel** 的统一接口：

```python
response = llm.invoke([SystemMessage("..."), HumanMessage("...")])   # 返回 AIMessage
response = await llm.ainvoke([...])                                   # 异步版本
for chunk in llm.stream([...]): ...                                   # 流式输出
llm_with_tools = llm.bind_tools(tools)                                # 绑定工具
```

输入是**消息列表**，输出是一条 **AIMessage**。

**Message 的四种角色：**

| 类型 | 角色 | 在你的 Agent 里 |
|---|---|---|
| `SystemMessage` | 系统指令 | `build_agent_system_prompt(today)` 每次现场拼接，不存入 State |
| `HumanMessage` | 用户输入 | `ainvoke({"messages": [HumanMessage(...)]})` |
| `AIMessage` | 模型输出，可带 `tool_calls` | `agent_node` 的返回值 |
| `ToolMessage` | 工具结果，带 `tool_call_id` | `ToolNode` 或超时分支生成 |

常用字段：`content`（内容）、`id`、`tool_calls`（仅 AIMessage）、`tool_call_id`（仅 ToolMessage）、`additional_kwargs` / `response_metadata`（厂商附带信息）、`usage_metadata`（Token 用量）。

**Tool** 对模型来说是「名称 + 描述 + 参数结构」，对运行时来说是「一个可调用的对象」。

**实践：**

你的 `get_chat_model(...)` 是项目自己封装的工厂函数，从参数看它大概处理了这些事（**推测，需对照 `llm_client.py` 确认**）：

| 参数 | 推测的作用 |
|---|---|
| `primary_env="LLM_MODEL"` | 从环境变量读取主模型名 |
| `fallback_env="LLM_MODEL_FALLBACKS"` | 读取备用模型，主模型失败时切换 |
| `timeout=40` | 单次请求超时 |
| `streaming=True` | 流式输出 |
| `enable_thinking=False` | 关闭模型的思考模式（降低延迟） |
| `tools=TOOLS` | 绑定工具（内部大概率调用 `bind_tools`） |

**局限与取舍：**

统一接口不能完全抹平厂商差异（比如并行工具调用、思考模式、流式细节），出问题时还是要看厂商文档。

---

### 3. @tool、Tool Schema、bind_tools()

#### 3.1 Tool Schema 如何定义（原 Day 10 内容，完整保留）

**定义：**

Tool Schema 是对工具名称、用途、输入参数和参数类型等信息的结构化描述。

**目的：**

让模型或调用方能够理解工具的用途，以及调用工具时应该传入什么参数。

**原理：**

一个工具 Schema 通常包含：

- name：工具名称。
- description：工具功能描述。
- inputSchema：输入参数结构。
- properties：参数字段及类型。
- required：必填参数。

例如：

```json
{
  "name": "search_news",
  "description": "根据关键词搜索新闻",
  "inputSchema": {
    "type": "object",
    "properties": {
      "keyword": {
        "type": "string",
        "description": "新闻搜索关键词"
      },
      "limit": {
        "type": "integer",
        "description": "返回新闻数量"
      }
    },
    "required": ["keyword"]
  }
}
```

模型根据工具名称、描述和参数 Schema 判断是否需要调用该工具，并生成对应参数。

**实践：**

AI 资讯项目中的新闻检索工具需要定义清晰的参数，例如关键词、返回数量等。

工具描述应该准确说明功能边界，避免模型混淆关键词检索和语义检索。

**局限与取舍：**

Schema 只能约束参数的结构和类型，不能完全保证参数符合业务逻辑。

例如，`limit` 虽然是整数，但还需要进一步限制合理范围。

因此，服务端仍然需要进行参数校验和异常处理，不能完全依赖模型生成正确参数。

#### 3.2 @tool：用函数生成工具（补充）

你的 `request_daily_report` 就是一个例子：

```python
@tool
async def request_daily_report(report_date: str, force: bool = False) -> str:
    """当指定日期的日报不存在，且用户确实需要日报时调用。
    后台生成日报，立即返回，不等待生成完成。
    用户明确要求重新生成时，force 设置为 true。"""
    return await trigger_report_generation(report_date, force)
```

`@tool` 自动从函数里提取三样东西：

| 提取来源 | 变成 |
|---|---|
| 函数名 `request_daily_report` | 工具 `name` |
| 文档字符串 docstring | 工具 `description`（模型靠它判断何时调用） |
| 参数名与类型注解 `report_date: str, force: bool = False` | 参数 Schema（有默认值的参数为非必填） |

生成的对应 Schema 大致是：

```json
{
  "name": "request_daily_report",
  "description": "当指定日期的日报不存在，且用户确实需要日报时调用。...",
  "parameters": {
    "type": "object",
    "properties": {
      "report_date": {"type": "string"},
      "force": {"type": "boolean", "default": false}
    },
    "required": ["report_date"]
  }
}
```

由此得到的实践要点：

1. **docstring 就是给模型看的说明书**，写得含糊，模型就会误用。你这里把「什么时候调用」「是否等待」「force 的含义」都写清楚了，是好习惯。
2. **类型注解就是参数约束**，注解错了，Schema 就错了。
3. 同步函数和 `async def` 都可以；在异步图里更推荐 `async def`。
4. 可以直接测试工具：`await request_daily_report.ainvoke({"report_date": "2026-11-09"})`。

#### 3.3 MCP 的工具怎么变成 LangChain 工具（补充）

MCP Server 返回的是 JSON Schema 格式的工具描述（见 3.1 的例子）。`load_mcp_tools` 会把**每一个 MCP 工具包装成一个 LangChain 工具对象**：

```text
MCP 工具描述（name / description / inputSchema）
        ↓ langchain-mcp-adapters 转换
LangChain 工具对象
   ├─ name、description：直接沿用
   ├─ args_schema：由 inputSchema 转换而来
   └─ 调用时执行：session.call_tool(name, arguments)
```

转换之后，**MCP 工具和本地 `@tool` 在 LangGraph 里完全等价**，所以你的 `TOOLS = list(mcp_tools) + [request_daily_report]` 才能把它们放进同一个列表。

#### 3.4 bind_tools()：把工具「告诉」模型（补充）

**定义：**

`llm.bind_tools(tools)` 返回一个新的可运行对象，每次请求都会把这些工具的名称、描述、参数 Schema 一起发送给模型。

**目的：**

模型必须知道「有哪些工具可用、每个怎么调」，才能决定是否调用以及生成什么参数。

**原理：**

```python
llm_with_tools = llm.bind_tools(TOOLS)
response = llm_with_tools.invoke(messages)
# response 是 AIMessage：
#   要调用工具 → response.tool_calls = [{"name": "...", "args": {...}, "id": "..."}]
#   直接回答   → response.tool_calls = []，内容在 response.content
```

不同厂商的工具格式不一样，LangChain 在 `bind_tools` 里负责转换：

| 厂商 | 请求里工具的格式（简化） |
|---|---|
| OpenAI 兼容 | `{"type":"function","function":{"name":..., "description":..., "parameters":{...}}}` |
| Anthropic | `{"name":..., "description":..., "input_schema":{...}}` |

模型返回的调用也被统一成 `AIMessage.tool_calls`，所以上层代码不需要改。

**实践：**

你的 `get_chat_model(..., tools=TOOLS)` 就是在初始化时完成了绑定（**需对照 `llm_client.py` 确认内部是否使用 `bind_tools`**）。因为绑定发生在 `init_agent()` 里、工具加载之后，所以必须先 `load_mcp_tools` 再创建 `agent_llm`。顺序反了，模型就看不到 MCP 工具。

**局限与取舍：**

- 工具描述每次请求都会占用 Token。工具越多、描述越长，开销越大，模型选择工具也越容易出错。这正是单 Agent 在工具变多后的局限（和 Day 9 第 6 节呼应）。
- 绑定的是静态列表。如果 MCP Server 之后新增了工具，需要重新加载并重新绑定。

---

### 4. Function Calling 与 Tool Calling 的关系（补充）

**定义：**

- Function Calling：OpenAI 最早提出的接口形式，模型可以输出「要调用某个函数及其参数」。
- Tool Calling：后来更通用的说法。「工具」是更宽泛的概念，一次响应里可以包含多个调用，每个带唯一的 id。

**目的：**

让模型从「只输出文本」变成「可以输出结构化的动作请求」，由程序来执行，再把结果还给模型。

**原理：**

```text
1. 应用把工具的 Schema 连同用户问题发给模型
2. 模型判断：直接回答，还是请求调用工具
3. 若请求调用：模型输出 {工具名, 参数, id}   ← 模型只是「提出请求」，并不执行
4. 应用执行工具，得到结果
5. 应用把结果（带 id）作为工具消息发回模型
6. 模型综合结果，给出最终回答（或继续请求下一次调用）
```

**两者的关系：**

| 对比 | Function Calling（早期） | Tool Calling（现行） |
|---|---|---|
| 概念范围 | 只有「函数」 | 「工具」，函数是其中一种 |
| 多个调用 | 早期一次一个 | 一次可返回多个（并行工具调用） |
| 调用标识 | 无 id | 每个调用有 `id`，结果通过 `tool_call_id` 对应 |
| 实际使用 | 旧接口 | 目前主流 |

现在大多数场景里这两个词基本可以互换，面试时可以说「**Function Calling 是 Tool Calling 的早期形态，现在通常指同一类能力**」。

**重要认知：模型从不执行工具。** **模型只输出结构化的调用请求**；真正执行的是你的代码（LangGraph 里是 `ToolNode`）。

**实践：**

在你的项目里，Tool Calling 对应的完整闭环：
```text
agent_llm 输出 AIMessage(tool_calls=[...])
   → route_after_agent 发现有 tool_calls
   → ToolNode 执行
   → 产出 ToolMessage(tool_call_id=...)
   → 回到 agent，模型读取结果
```

**局限与取舍：**

- 模型可能选错工具、编造参数，或者重复调用。所以工具层要做参数校验和调用次数限制。
- 并行工具调用提高效率，但要注意工具之间不能有隐含依赖。

---

### 5. MCP Host、Client、Server，Tools、Resources、Prompts（原 Day 10 内容，完整保留并补充）

**定义：**

MCP（Model Context Protocol）是一种用于连接 AI 应用与外部工具、数据资源的开放协议。

主要组成：

- MCP Host：承载 AI 应用的主体。
- MCP Client：负责与 MCP Server 建立连接和通信。
- MCP Server：向外提供工具、资源和提示模板。
- Tools：可执行的工具。
- Resources：可读取的数据资源。
- Prompts：可复用的提示模板。

**目的：**

统一 AI 应用接入外部工具和数据的方式，减少不同 AI 应用与外部服务之间重复开发适配代码的问题。

**原理：**

基本关系：

```text
MCP Host（AI 应用）
       ↓
MCP Client
       ↓
MCP Server
       ↓
Tools / Resources / Prompts
       ↓
外部数据库、API 或其他服务
```

Client 与 Server 建立连接后，可以发现 Server 提供的能力，再按照 MCP 协议进行调用。

三种能力的区别：

| 类型 | 主要作用 | 示例 |
|---|---|---|
| Tools | 执行操作 | 搜索新闻、生成日报 |
| Resources | 提供数据 | 新闻数据、文件内容 |
| Prompts | 提供提示模板 | 新闻分析模板 |

**实践：**

AI 资讯项目中，通过 MCP Server 暴露以下工具：

- `search_news`：关键词检索新闻。
- `search_news_semantic`：语义检索新闻。
- `get_daily_report`：获取已有日报。
- `request_daily_report`：请求生成日报。

Agent 可以通过这些工具访问项目内部的数据和功能。

**局限与取舍：**

MCP 负责规范工具和数据能力的接入，不负责 Agent 的任务规划和推理。

Tools、Resources、Prompts 的用途不同，不能简单互相替代。对于需要执行操作的场景，通常使用 Tools。

#### 补充 5-1：Host、Client、Server 在你的项目里分别是谁

| 角色 | 你的项目里 | 说明 |
|---|---|---|
| Host | 整个 Agent 服务进程（FastAPI + LangGraph + LLM 调用） | 面向用户的 AI 应用 |
| Client | `MultiServerMCPClient` 创建的会话 | Host 内部，一个 Client 对应一个 Server 的连接 |
| Server | `mcp_server/news_mcp.py`，被当作子进程启动 | 暴露工具并执行业务逻辑 |

一个 Host 可以同时连接多个 Server（`MultiServerMCPClient` 的 Multi 就是这个意思），每个 Server 一条独立连接。

**注意一个和你笔记不完全一致的地方：** 你的代码里，`request_daily_report` 是用 `@tool` 定义的**本地工具**，在 `init_agent()` 中与 MCP 工具拼接，并不在 MCP Server 里。你的笔记把它列在 MCP 暴露的工具里，面试时要核对 `news_mcp.py` 的实际内容再回答。

按代码推测它没有放进 MCP 的原因（**这是推测**）：它依赖本进程里的 `_GEN_LOCKS` 和 `BACKGROUND_TASKS`（同一进程内的锁与后台任务），放在独立的 MCP 子进程里就和 Agent 进程分离了，不方便统一管理。

#### 补充 5-2：三种能力谁来控制

| 类型 | 控制方 | 说明 |
|---|---|---|
| Tools | 模型决定是否调用（Model-controlled） | 模型根据描述自主选择 |
| Resources | 应用决定读取哪些（Application-controlled） | 由 Host 选择加载给模型的数据，通常用 URI 标识，如 `news://latest` |
| Prompts | 用户主动选择（User-controlled） | 例如用户在界面里选一个「分析新闻」模板 |

你的项目目前只使用了 Tools，没有用到 Resources 和 Prompts。`load_mcp_tools` 加载的也只有 Tools。

#### 补充 5-3：协议的基本交互

MCP 基于 JSON-RPC 2.0 消息通信，典型生命周期：

```text
Client                                   Server
  │── initialize（版本、能力协商）──────────▶│
  │◀──────────── 返回 Server 能力、信息 ─────│
  │── notifications/initialized ───────────▶│     握手完成
  │── tools/list ──────────────────────────▶│     发现工具
  │◀──────────── 工具列表（含 inputSchema）──│
  │── tools/call {name, arguments} ────────▶│     调用工具
  │◀──────────── 结果 content[] ─────────────│
```

**传输方式（Transport）常见有两种：**

| 传输 | 说明 | 你的项目 |
|---|---|---|
| stdio | Client 把 Server 作为**子进程启动**，通过标准输入输出通信 | 使用这种（`"transport": "stdio"`） |
| Streamable HTTP | 通过 HTTP 通信，Server **可独立部署、被多个客户端访问** | 未使用 |

**stdio 的一个重要陷阱：** 标准输出被协议占用，MCP Server 里不能随便 `print()` 到 stdout，否则会破坏消息流。日志要输出到 stderr 或写文件。如果你的 `news_mcp.py` 里有 `print`，要核对一下。

---

### 6. MultiServerMCPClient 与 load_mcp_tools()（补充）

**定义：**

- `MultiServerMCPClient`：`langchain-mcp-adapters` 提供的客户端，可以按配置同时管理多个 MCP Server 的连接。
- `load_mcp_tools(session)`：**从一个已建立的 MCP 会话里读取工具列表，并转换成 LangChain 工具。**

**目的：**

省去手写 **MCP 协议细节（握手、列出工具、调用、结果转换）的工作**，让 MCP 工具能直接用在 LangChain / LangGraph 里。

**原理：**

你的配置：

```python
client = MultiServerMCPClient({
    "news_mcp": {         # 自定义的 Server 名称，后面用它取会话
        "command": sys.executable,   # 用当前 Python 解释器启动，避免找错 python
        "args": [MCP_SCRIPT_PATH],       # Server 脚本路径
        "transport": "stdio",            # 传输方式
        "env": os.environ.copy(),        # 把当前环境变量传给子进程（数据库路径、密钥等）
    }
})
```

两种获取工具的方式：

| 方式 | 代码 | 会话特点 |
|---|---|---|
| 无状态 | `await client.get_tools()` | 每次调用工具时**新建**会话，调用完关闭。stdio 下就是每次拉起一个子进程 |
| 持久会话 | `session = await client.session("news_mcp")` + `load_mcp_tools(session)` | **整个服务共用一个会话，一个子进程** |

对应你的代码：

```python
session = await _exit_stack.enter_async_context(client.session("news_mcp"))
tools = await load_mcp_tools(session)           # 持久会话（优先）
...
return await client.get_tools()                 # 失败时回退为无状态
```

`load_mcp_tools` 内部做的事：向 Server 发 `tools/list` → 为每个工具生成 LangChain 工具对象 → 对象被调用时执行 `session.call_tool(...)`。

**实践：**

为什么**优先持久会话**：

- 无状态方式每次调用工具都要启动一个 Python 子进程、重新 import 模块、可能还要重新连数据库，**延迟明显增加**。
- **持久会话只启动一次**，后续调用只是在已有的管道里发消息。

**局限与取舍：**

- 持久会话把工具和**这一个会话**绑在一起：会话断开（子进程崩溃、管道被关）后，所有工具调用都会失败，需要重建会话并重新加载工具。
- 你的回退逻辑只在**启动时**生效；运行中会话断了，不会自动恢复。
- 在持久会话上，调用被 `asyncio.wait_for` 超时取消后，会话状态可能受影响，需要观察并考虑重建机制。

---

### 7. MCP Session 与 AsyncExitStack（补充）

**定义：**

- MCP Session：Client 与 Server 之间一条**已初始化的连接**，在它存活期间可以多次发请求。
- `AsyncExitStack`：Python 标准库工具，用来**手动管理**一个或多个异步上下文管理器的进入和退出。

**目的：**

`client.session(...)` 是一个异步上下文管理器，正常写法是：

```python
async with client.session("news_mcp") as session:
    tools = await load_mcp_tools(session)
    ...
# 离开 with 块，会话就关闭了，子进程也退出
```

这样会话的寿命只在 `with` 块内。但你需要会话在**整个服务运行期间**都保持打开，而不是只在一个代码块里。

**原理：**

```python
_exit_stack = AsyncExitStack()
session = await _exit_stack.enter_async_context(client.session("news_mcp"))   # 相当于手动「进入」
tools = await load_mcp_tools(session)
# ……会话保持打开，服务一直在用……

await _exit_stack.aclose()                                                   # 相当于手动「退出」
```

| 写法 | 会话何时关闭 |
|---|---|
| `async with` | **离开代码块时自动关闭** |
| `AsyncExitStack` | 你调用 `aclose()` 时才关闭 |

退出时按**后进先出**的顺序关闭所有已注册的上下文。

**实践：**

**你的生命周期管理：**
```text
FastAPI 启动  → init_agent() → enter_async_context(...)  # 打开会话，启动 MCP 子进程
……处理请求……                    # 所有工具调用共用这一个会话
FastAPI 关闭  → close_agent() → _exit_stack.aclose()      # 关闭会话，回收子进程
```

`_load_mcp_tools_persistent` 的异常处理：打开会话失败时，先 `aclose()` 清理，再回退到 `client.get_tools()`（无状态）。注意回退分支里 `_exit_stack` 被置为 `None`，`close_agent()` 里就不会重复关闭。

**局限与取舍：**

- 手动管理意味着**必须记得关闭**，否则子进程会残留。务必在应用关闭钩子里调用 `close_agent()`。
- 底层使用的异步库对「在哪个任务里进入、在哪个任务里退出」有要求，进入和退出如果不在同一个异步任务里，可能出现类似 `cancel scope` 的报错。FastAPI 的 lifespan 里启动和关闭通常在同一任务，一般没问题；但放在不同的请求或后台任务里就可能出问题。
- 更简单的替代写法：在 FastAPI 的 `lifespan` 里直接 `async with client.session(...)` 然后 `yield`，让会话天然跟随应用生命周期。

LangGraph 的 checkpointer 负责把每个 thread_id 的对话状态（messages）存下来，这样下一次请求用同一个 thread_id 时，agent 能接着之前的上下文，服务重启后也不会丢。用 SQLite 作为存储，所以需要一个数据库连接，aiosqlite 的**连接内部会起一个后台线程来执行 SQLite 操作，所以它是一个需要显式关闭的资源**。

conn 没有放进 _exit_stack，也没有存成全局变量，close_agent() 就没有办法关它。后果：
  - 进程退出时，aiosqlite 的后台线程可能让进程卡住不退出（取决于版本）。
  - SQLite 连接没有正常关闭，通常数据不会丢（每次写入都已提交），但不够干净
已关闭
```Python
  if _checkpointer_conn:
  await _checkpointer_conn.close()
  _checkpointer_conn = None
  ```
### 8. MCP 和普通 HTTP API 有什么区别？（原 Day 10 内容，完整保留并补充）

**定义：**

HTTP API 是应用之间通过 HTTP 请求和响应进行通信的接口。
MCP 是面向 AI 应用的协议，规范了工具发现、工具调用以及资源和提示模板的交互方式。

**目的：**

HTTP API 解决通用服务之间的通信问题。
MCP 进一步解决 AI 应用如何标准化地发现和使用外部能力的问题。

**原理：**

普通 HTTP API：

```text
调用方
  ↓
提前知道接口地址和参数
  ↓
发送 HTTP 请求
  ↓
服务端处理
  ↓
返回响应
```

MCP：

```text
AI 应用
  ↓
MCP Client
  ↓
发现 Server 提供的能力
  ↓
选择工具并传递参数
  ↓
MCP Server 执行
  ↓
返回工具结果
```

**实践：**

AI 资讯项目中，原本的 Python 新闻查询函数可以通过 MCP Server 封装成工具。
Agent 不需要直接了解底层数据库查询逻辑，而是通过 MCP 工具调用获取新闻结果。

**局限与取舍：**

MCP 不是 HTTP API 的替代品，MCP Server 本身也可以通过 HTTP 等传输方式通信。
如果只是普通业务服务之间的简单调用，直接使用 HTTP API 可能更加轻量。
如果需要让不同 AI 客户端以统一方式发现和调用工具，MCP 更合适。

#### 补充 8-1：对比表

| 维度 | 普通 HTTP API | MCP |
|---|---|---|
| 面向对象 | 通用的程序与程序 | 专门面向 AI 应用 |
| 能力发现 | 靠文档（OpenAPI 等）事先约定，调用方要提前知道 | 运行时通过 `tools/list` 动态发现，附带 Schema |
| 调用方式 | 每个服务自己的路径、方法、参数格式 | 统一的 `tools/call`，参数格式统一为 JSON Schema |
| 能力类型 | 无统一划分 | Tools / Resources / Prompts 三类 |
| 连接方式 | 无状态请求响应为主 | 有会话（初始化握手、能力协商），可有通知 |
| 传输 | HTTP | stdio、Streamable HTTP 等 |
| 生态 | 任意 | 一个 MCP Server 可被多个 MCP 客户端直接使用 |

#### 补充 8-2：在你的项目里，MCP 的收益和代价

收益：

- 工具实现与 Agent 解耦：新闻检索逻辑放在 `news_mcp.py`，Agent 只关心工具名和参数。
- **工具自带 Schema，Agent 启动时自动发现，不需要手写工具描述**。
- 同一个 MCP Server 之后可以被别的 MCP 客户端复用。

代价：

- 多一个子进程，多一层序列化和进程间通信。
- **需要管理会话生命周期**（见第 7 节）。
- stdio 下标准输出不能乱用。
- 调试链路变长（**Agent → Client → Server → 数据库**）。

面试时可以这样回答「为什么用 MCP」：我们这个项目工具数量不多，MCP 带来的最大价值是**解耦和标准化**，而不是性能；如果只是同一进程内调用，直接写 `@tool` 更轻量，我也在 `request_daily_report` 上就是这么做的。

---

### 9. MCP 如何让 Agent 调用外部工具？（原 Day 10 内容，完整保留）

**定义：**

MCP 通过 Client 和 Server 之间的协议通信，让 AI 应用能够发现并调用外部服务提供的工具。

**目的：**

将 Agent 的决策能力与具体工具实现解耦，使 Agent 可以使用不同 MCP Server 提供的外部能力。

**原理：**

一次完整调用过程：

1. MCP Client 与 MCP Server 建立连接。
2. Client 获取 Server 提供的工具列表。
3. AI 应用将工具描述提供给模型。
4. 模型根据用户问题选择工具并生成参数。
5. Agent 将工具调用请求交给 MCP Client。
6. Client 通过 MCP 协议请求 Server 执行工具。
7. Server 执行实际业务逻辑并返回结果。
8. Agent 将工具结果交给模型，生成最终回答。

完整流程：

```text
用户问题
   ↓
Agent
   ↓
LLM 选择工具
   ↓
MCP Client
   ↓
MCP Server
   ↓
执行 Tool
   ↓
返回工具结果
   ↓
Agent / LLM
   ↓
最终回答
```

**实践：**

AI 资讯项目中，Agent 根据用户问题选择 `search_news` 或 `search_news_semantic` 等工具。

MCP Server 负责执行具体新闻查询逻辑，并将结果返回给 Agent。

**局限与取舍：**

MCP 只是工具接入和通信协议，不能保证工具执行一定成功。
需要处理连接失败、调用超时、参数错误和工具返回异常等情况。
另外，外部工具可能涉及数据库写入或其他有副作用的操作，需要做好权限控制。

#### 补充 9-1：对应到你的代码，上面 8 步分别发生在哪里

| 步骤 | 代码位置 |
|---|---|
| 1. 建立连接 | `init_agent()` → `_load_mcp_tools_persistent()` → `client.session("news_mcp")`（拉起子进程并完成握手） |
| 2. 获取工具列表 | `load_mcp_tools(session)`（`tools/list`） |
| 3. 把工具描述给模型 | `get_chat_model(..., tools=TOOLS)`（`bind_tools`） |
| 4. 模型选工具、生成参数 | `agent_node` → `agent_llm.ainvoke(...)` → ❗`AIMessage.tool_calls` |
| 5. 交给 Client | `route_after_agent` → `Send` → `_run_tool_group` → `ToolNode.ainvoke` → 工具对象被调用 |
| 6. 协议请求 Server | 适配层执行 `session.call_tool(name, arguments)`（`tools/call`） |
| 7. Server 执行业务 | `news_mcp.py` 里的函数查询数据库并返回 |
| 8. 结果交回模型 | 结果被包装成 `ToolMessage` → 回到 `agent_node` → 最终回答 |

---❗

### 10. 完整调用链：从用户提问到 MCP Server 执行工具（补充）

#### 10.1 总览图⭐

```text
┌──────────────────────── Agent 进程（MCP Host）────────────────────────┐
│                                                                        │
│  用户问题                                                               │
│     │  app.ainvoke({"messages":[Human]}, thread_id)                    │
│     ▼                                                                  │
│  agent_node ──▶ LLM 服务（HTTP）  ◀─ 请求里附带所有工具的 Schema         │
│     │            返回 AIMessage(tool_calls=[search_news(...)])         │
│     ▼                                                                  │
│  route_after_agent ──▶ Send("tools_search")                           │
│     ▼                                                                  │
│  _run_tool_group ──▶ ToolNode ──▶ 工具对象（MCP 适配）                  │
│                                      │ session.call_tool()             │
│                                      ▼                                 │
│                               MCP Client 会话 ──┐                      │
└──────────────────────────────────────────────────┼──────────────────────┘
                                   stdin/stdout 管道 │  JSON-RPC: tools/call
┌──────────────────────────────────────────────────▼──────────────────────┐
│  MCP Server 子进程（news_mcp.py）                                        │
│     工具函数 search_news(keyword=...) ──▶ 数据库 / 检索                   │
│     返回 content[] ─────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────────────┘
        ▲ 结果沿原路返回 → ToolMessage → 回到 agent_node → LLM 生成最终回答
```

#### 10.2 逐步展开

以「给我强化学习相关新闻」为例：

| # | 阶段 | 发生了什么 |
|---|---|---|
| 1 | 启动 | `init_agent()`：启动 MCP 子进程，握手，`tools/list`，得到 `search_news` 等工具；与本地 `request_daily_report` 合并为 `TOOLS`；创建绑定工具的 `agent_llm`；创建 Checkpointer 并编译图 |
| 2 | 入口 | `ainvoke({"messages":[HumanMessage(...)]}, config={thread_id,...})`，恢复该线程历史并追加新消息 |
| 3 | 决策 | `agent_node`：System Prompt + 裁剪后的历史送给 LLM；请求里带着所有工具 Schema |
| 4 | 模型输出 | LLM 返回 `AIMessage(tool_calls=[{"name":"search_news","args":{"keyword":"强化学习"},"id":"call_1"}])` |
| 5 | 路由 | `route_after_agent` 发现有 `tool_calls`，按分组返回 `[Send("tools_search", state)]` |
| 6 | 工具执行 | `_run_tool_group` 过滤本组调用，`ToolNode` 按名称找到 `search_news` 工具对象并调用，外面包着 30 秒超时 |
| 7 | MCP 通信 | 工具对象通过持久会话向子进程发送 `tools/call`：`{"name":"search_news","arguments":{"keyword":"强化学习"}}` |
| 8 | Server 执行 | `news_mcp.py` 里对应函数运行，查询数据库，返回结果 |
| 9 | 结果回传 | JSON-RPC 响应里的 `content` 被适配层转换为文本，`ToolNode` 包成 `ToolMessage(tool_call_id="call_1")` |
| 10 | 再次决策 | 回到 `agent_node`，LLM 读到工具结果，不再调用工具，生成最终回答 |
| 11 | 结束 | 路由发现没有 `tool_calls` → END；每个 superstep 都保存了 Checkpoint；`ainvoke` 返回，取 `r["messages"][-1].content` |

协议层面实际传输的消息大致是：

```json
// Client → Server
{"jsonrpc":"2.0","id":3,"method":"tools/call",
 "params":{"name":"search_news","arguments":{"keyword":"强化学习","limit":5}}}

// Server → Client
{"jsonrpc":"2.0","id":3,
 "result":{"content":[{"type":"text","text":"1. ...\n2. ..."}],"isError":false}}
```

`isError` 为 `true` 时表示工具执行出错，适配层会把它转成错误信息，由 ToolNode 返回给模型。

#### 10.3 本地工具 `request_daily_report` 的路径不一样

```text
agent_node → AIMessage(tool_calls=[request_daily_report(...)])
   → route_after_agent → Send("tools_report")
   → ToolNode → 直接调用本地 Python 函数（不经过 MCP）
        ├─ 校验日期、按日期加锁
        └─ asyncio.to_thread 启动后台 daily_flow，立即返回「已启动」
   → ToolMessage → agent 回复用户「正在生成，请稍后查询」
```

对 Agent 来说两类工具用法完全一致，区别只在工具对象内部：一个走 MCP 协议，一个直接调用本地函数。

#### 10.4 各环节可能出问题的地方（和停止条件、超时的联系）⭐

| 环节 | 可能的问题 | 现有处理 |
|---|---|---|
| LLM 请求 | 超时、限流 | `timeout=40`、备用模型 |
| 模型生成参数 | 参数不合法、重复调用 | 基本没有业务层防护 |
| 工具执行 | 超过 30 秒 | `asyncio.wait_for` + 超时 ToolMessage |
| MCP 会话 | 子进程崩溃、管道断开 | 只在启动时回退，运行时没有自动恢复 |
| Server 业务 | 数据库异常、返回为空 | 取决于 `news_mcp.py` 的实现 |
| 整个循环 | 模型反复调用工具 | 只有 `recursion_limit` 兜底 |

---

### 11. 最小 MCP Demo（对应实践任务）

下面三段代码可以放在同一个目录下依次运行，帮助理解 Server、Client、LangChain 适配层之间的关系。需要先安装依赖：`pip install mcp langchain-mcp-adapters`。

#### 11.1 一个最小的 MCP Server

```python
# demo_news_mcp.py
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("demo-news")

@mcp.tool()
def search_news(keyword: str, limit: int = 5) -> str:
    """根据关键词搜索新闻。keyword 是关键词，limit 是返回条数（1-20）。"""
    limit = max(1, min(limit, 20))          # 服务端自己校验范围，不依赖模型
    return "\n".join(f"{i + 1}. 关于「{keyword}」的新闻标题 {i + 1}" for i in range(limit))

@mcp.resource("news://latest")
def latest_news() -> str:
    """Resource 示例：一份可读取的数据。"""
    return "最新新闻列表（示例数据）"

@mcp.prompt()
def analyze_news(title: str) -> str:
    """Prompt 示例：可复用的提示模板。"""
    return f"请从事件、影响、风险三个角度分析这条新闻：{title}"

if __name__ == "__main__":
    mcp.run(transport="stdio")       # 注意：stdio 模式下不要 print 到 stdout
```
对照你项目里的 `news_mcp.py` 看这几点（**以你的实际文件为准**）：工具是怎么注册的、`description` 怎么写的、有没有参数校验、有没有 `print` 到 stdout、启动方式是不是 stdio。

#### 11.2 用官方 SDK 直接跑一遍协议（看清握手、发现、调用）

```python
# demo_raw_client.py
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable, args=["demo_news_mcp.py"])
    async with stdio_client(params) as (read, write):          # 启动子进程，建立管道
        async with ClientSession(read, write) as session:
            await session.initialize()                          # ① 握手
            tools = await session.list_tools()                  # ② 发现工具
            for t in tools.tools:
                print(t.name, "|", t.description)
                print("   schema:", t.inputSchema)             # 看看 Tool Schema 长什么样
            result = await session.call_tool("search_news", {"keyword": "强化学习", "limit": 2})   # ③ 调用
            print(result.content)

asyncio.run(main())
```
运行后对照第 5 节补充 5-3 的时序图，能把「initialize → tools/list → tools/call」三步和输出一一对应。

#### 11.3 用 LangChain 适配层（和你的项目一致）⭐

```python
# demo_adapter_client.py
import asyncio, sys
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

CONFIG = {
    "demo": {
        "command": sys.executable,
        "args": ["demo_news_mcp.py"],
        "transport": "stdio",
    }
}

async def main():
    client = MultiServerMCPClient(CONFIG)

    # 方式 A：无状态，每次调用工具都会新建会话（stdio 下 = 每次启动子进程）
    tools = await client.get_tools()
    print("A:", [t.name for t in tools])
    print(await tools[0].ainvoke({"keyword": "强化学习", "limit": 2}))

    # 方式 B：持久会话，复用同一个子进程（你的项目优先用这种）
    async with client.session("demo") as session:
        tools = await load_mcp_tools(session)
        print("B:", [t.name for t in tools])
        print(tools[0].args)                       # LangChain 工具的参数 Schema
        print(await tools[0].ainvoke({"keyword": "大模型", "limit": 3}))

asyncio.run(main())
```

自测问题：

1. 方式 A 和方式 B 在耗时上有什么区别？可以用 `time.perf_counter()` 连续调用 5 次对比。
2. 把 `async with` 块之外再调用 `tools[0].ainvoke(...)`，会发生什么？（会话已关闭，这就是你的项目需要 `AsyncExitStack` 的原因。）
3. 在 Server 里加一行 `print("debug")`，运行 11.2，会发生什么？（破坏 stdio 协议，客户端可能解析报错。）

#### 11.4 接入 LangGraph

得到 `tools` 之后，接入 Day 9 的图只需要两步：

```python
llm_with_tools = llm.bind_tools(tools)      # 让模型看到工具
tool_node = ToolNode(tools)                 # 让图能执行工具
```

其余结构（agent 节点、条件路由、回到 agent）和 Day 9 第 15 节的最小 Demo 一致。

---

## 二、实践任务

- [ ] 找到项目的 MCP Server 代码。（`mcp_server/news_mcp.py`，对照 11.1 看它如何注册工具、有无 print、有无参数校验）
- [ ] 跟踪一次 MCP 工具调用。（对照第 10 节的 11 步，在每一步加日志或断点，亲眼看到 `tool_calls`、`tools/call`、`ToolMessage`）
- [ ] 解释 Agent、MCP Client、MCP Server 之间的关系。（见第 5 节补充 5-1）
- [ ] 检查项目是否真正使用了 Checkpoint，不要把了解的功能说成已经实现。（见 `09-langgraph.md` 第 11 节补充 11-3）
- [ ] 确认 `request_daily_report` 到底是 MCP 工具还是本地工具，并更正笔记。
- [ ] 打印 `[(t.name, t.args) for t in TOOLS]`，看清每个工具给模型的 Schema 是什么样。
- [ ] 运行第 11 节三个 Demo，并自己改一个工具（比如加一个 `get_daily_report`）。

---

## 三、学习复盘

**今天还没搞懂的内容：**

- Checkpointer 如何根据 Thread ID 保存和恢复状态？状态持久化与长期记忆有什么区别？（见 `09-langgraph.md` 第三节的回答）
- MCP 工具调用时，Client 如何发现工具，Server 又如何执行工具？

**需要面试前回顾的内容：**

- Checkpointer、Thread ID、Checkpoint 分别是什么？（见 `09-langgraph.md`）
- MCP Client、Server、Tools、Resources、Prompts 有什么区别？
- MCP 和普通 HTTP API 有什么区别？
- Tool Schema 有什么作用？为什么服务端还需要进行参数校验？
- Agent 如何通过 MCP 调用外部工具？

### 对上面「没搞懂」问题的回答（补充）

**MCP 工具调用时，Client 如何发现工具，Server 又如何执行工具？**

- 发现：连接建立并握手后，Client 发送 `tools/list`，Server 返回每个工具的 `name`、`description`、`inputSchema`。`load_mcp_tools` 把它们转换成 LangChain 工具，再通过 `bind_tools` 告诉模型。
- 执行：模型产出 `tool_calls` 后，`ToolNode` 调用对应工具对象，适配层向 Server 发送 `tools/call`（带工具名和参数）。Server 根据名称找到注册的函数，执行业务逻辑，把结果封装成 `content` 返回。

---

## 四、项目代码中值得注意的细节（面试可主动提，也是后续优化点）

1. **笔记与代码不一致**：`request_daily_report` 在代码里是本地 `@tool`，不是 MCP 工具。
2. **持久会话运行时无自愈**：回退逻辑只在启动时生效，会话中途断开后工具会持续失败，需要重建会话并重新加载、重新绑定工具。
3. **`wait_for` 取消后会话状态**：超时取消持久会话上的调用，可能影响后续调用，要观察并考虑重建。
4. **`AsyncExitStack` 必须被关闭**：确保 `close_agent()` 在应用关闭时被调用，否则子进程残留。
5. **stdio 不能乱 print**：`news_mcp.py` 里的日志必须走 stderr 或日志文件。
6. **工具 Schema 的质量**：描述里要写清关键词检索和语义检索的区别，`limit` 等参数要在服务端限制范围。
7. **工具执行有副作用时要有权限控制**：`request_daily_report` 会触发后台任务，需要防重复触发（你已经用按日期的锁做了）。
8. **绑定是静态的**：Server 新增工具后，Agent 需要重新加载才能看到。

---

## 五、面试高频问答（精简版）

**Q1：LangChain 和 LangGraph 是什么关系？**
答：LangChain 是组件库（模型接口、消息、工具），LangGraph 是编排运行时（状态、循环、持久化）。我的项目用 LangChain 的消息和工具类型，用 LangGraph 把它们组织成「agent ↔ tools」的循环。

**Q2：`@tool` 做了什么？`bind_tools` 做了什么？**
答：`@tool` 从函数名、docstring、类型注解生成工具的名称、描述和参数 Schema。`bind_tools` 把这些 Schema 附在每次请求里发给模型，并负责转换成不同厂商要求的格式，模型才能决定调用哪个工具、生成什么参数。

**Q3：Function Calling 和 Tool Calling 有什么区别？**
答：Tool Calling 是更通用的叫法，Function Calling 是早期形态，现在基本指同一类能力。关键点是模型只负责「提出调用请求」，执行由应用完成，结果通过 `tool_call_id` 交还给模型。

**Q4：MCP 是什么？和 HTTP API 有什么区别？**⭐
答：MCP 是面向 AI 应用的协议，规范了工具的发现、调用，以及资源和提示模板。HTTP API 是通用通信接口，调用方要事先知道接口约定；MCP 让客户端在运行时通过 `tools/list` 发现工具及其 Schema，并用统一的 `tools/call` 调用。它不是 HTTP 的替代品，MCP 也可以跑在 HTTP 之上。

**Q5：Host、Client、Server 分别是什么？**
答：Host 是 AI 应用本身（我的 Agent 服务），Client 是 Host 内部与某个 Server 的连接（`MultiServerMCPClient` 的会话），Server 是暴露工具的程序（`news_mcp.py`，作为 stdio 子进程运行）。

**Q6：Tools、Resources、Prompts 的区别？**
答：Tools 是可执行的操作，由模型决定调用；Resources 是可读取的数据，由应用选择加载；Prompts 是可复用的提示模板，由用户选择。我的项目只用了 Tools。

**Q7：为什么要用持久会话和 `AsyncExitStack`？**⭐
答：无状态方式每次调用工具都会启动一个新子进程，延迟高。持久会话让整个服务只启动一个子进程。但 `async with` 离开代码块就会关闭会话，所以用 `AsyncExitStack` 手动管理，在初始化时打开、在应用关闭时关闭。代价是必须保证关闭，否则子进程残留。

**Q8：从用户提问到工具执行，完整经过哪些步骤？**
答：（按第 10.2 节的 11 步回答：入口恢复历史 → agent 带工具 Schema 调 LLM → 输出 `tool_calls` → 条件路由 `Send` → `ToolNode` 执行 → 适配层发 `tools/call` → Server 查库返回 → `ToolMessage` 回到 agent → 生成最终回答 → END 并保存 Checkpoint。）

**Q9：用 MCP 有什么代价？为什么 `request_daily_report` 没放进 MCP？**
答：代价是多一个进程、多一层通信、会话生命周期要管理、stdio 下不能乱 print。`request_daily_report` 依赖本进程里的锁和后台任务，直接用本地 `@tool` 更简单（这是我根据代码做的判断，面试前我会再和自己的设计意图核对一次）。

**Q10：工具调用失败怎么办？**⭐
答：分层处理：工具层做参数校验；工具组加 30 秒超时，超时返回 ToolMessage 而不是让图崩溃；图层有 `recursion_limit` 兜底。我也知道这个方案还缺业务层的循环保护和会话重建，已经有改进方案。
