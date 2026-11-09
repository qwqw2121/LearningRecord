# Day 9｜LangGraph

> 本文件 = 原 Day 9 全部内容（保留）+ 原 Day 10 中 Checkpointer / 状态持久化内容（保留，移到本文件第 11、12 节）+ 结合 Agent 源码补充的执行机制。
> 标注「**补充**」的部分是新增内容；未标注的是原有笔记。
> 项目源码中看不到的文件（`llm_client.py`、`prompts.py`、`news_mcp.py`）里的内容，凡是推测的地方都会标明「需对照源码确认」。

## 技术面试回答结构

1. 定义：它是什么？用自己的话解释概念
2. 目的：为什么需要它？理解它解决什么问题
3. 原理：它内部怎么工作？理解核心机制
4. 实践：我在项目中怎么使用？
5. 取舍：有什么局限，为什么选择它？

---

## 零、先看全局：你的 Agent 源码结构

### 0.1 一张图看懂执行流程

```text
                 ┌─────────────────────────────┐
用户提问 ───────▶│  app.ainvoke(input, config) │  config 里带 thread_id
                 └──────────────┬──────────────┘
                                ▼
                       ┌─────────────────┐
              ┌───────▶│   agent 节点     │  裁剪历史 → LLM 决策
              │        └────────┬────────┘
              │                 ▼
              │        route_after_agent()
              │         │         │          │
              │   无 tool_calls   │ 有 tool_calls（按分组 Send）
              │         │         ├──────────────┐
              │         ▼         ▼              ▼
              │       END   tools_search     tools_report   ← 同一步并行
              │                   │              │
              └───────────────────┴──────────────┘
                     ToolMessage 写回 messages，回到 agent
```

### 0.2 源码分块 → 知识点对照表

| 源码位置 | 作用 | 对应知识点（本文件章节） |
|---|---|---|
| `build_graph()` | 定义节点、边、条件路由并编译 | 1、2、13 |
| `MessagesState` | 图的 State，内置 `messages` 字段 | 1、3 |
| `agent_node` | 裁剪历史 → 调 LLM → 返回 AIMessage | 7、10 |
| `route_after_agent` | 条件路由，返回 `END` 或 `Send` 列表 | 2、8 |
| `_run_tool_group` + `tools_*_node` | 按分组执行工具，带超时 | 4、8 |
| `trim_messages` / `_shrink` | 控制送入 LLM 的上下文大小 | 10 |
| `_make_async_checkpointer` | 创建 `AsyncSqliteSaver` | 11、12 |
| `ainvoke` / `main()` | 异步入口 | 9 |
| `request_daily_report` / `trigger_report_generation` | 本地工具，后台线程生成日报 | 7、14 |
| `init_agent` / `close_agent` | 初始化、关闭（MCP 会话见 Day 10） | 13 |

---

## 一、学习内容与记录

### 1. StateGraph、State、Node、Edge

**定义：**

LangGraph 是一个用于构建有状态、多步骤 Agent 工作流的框架。

- StateGraph：定义整个图结构。
- State：保存工作流执行过程中的共享状态。
- Node：执行具体任务的节点，通常是一个函数。
- Edge：定义节点之间的执行关系。

**目的：**

将复杂的 Agent 执行流程拆分成多个节点，通过状态传递和边连接控制执行过程。

**原理：**

一个典型流程：

```text
用户输入
   ↓
Agent Node
   ↓
判断是否调用工具
   ├── 是 → Tool Node → Agent Node
   └── 否 → END
```

Node 接收当前 State，执行任务后返回状态更新。Edge 决定下一个执行节点。

**实践：**

在 AI 资讯项目中，找到 LangGraph 工作流的构建代码，理解 State 保存了哪些信息，以及 Agent 节点如何调用工具。

**局限与取舍：**

LangGraph 提供了较强的流程控制能力，但也增加了代码结构和状态管理复杂度。简单的单次模型调用不一定需要使用 LangGraph。

#### 补充 1-1：四个概念在你的代码里分别是什么

| 概念 | 你的代码 | 说明 |
|---|---|---|
| StateGraph | `g = StateGraph(MessagesState)` | 图的「构建器」，参数是 State 的类型 |
| State | `MessagesState` | 预置的 State，只有一个字段 `messages` |
| Node | `agent_node`、`tools_search_node`、`tools_report_node` | 普通函数（这里都是 `async def`） |
| Edge | `add_edge(...)`、`add_conditional_edges(...)` | 固定边和条件边 |
| 入口 | `set_entry_point("agent")` | 等价于 `add_edge(START, "agent")` |
| 出口 | `END` | 虚拟终点节点 |

`MessagesState` 的定义等价于：

```python
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

关键在 `Annotated[..., add_messages]`：它给 `messages` 字段绑定了 Reducer（见第 3 节）。

#### 补充 1-2：Node 的输入输出约定

```python
async def agent_node(state: MessagesState):    # 输入：当前完整 State
    ...
    return {"messages": [response]}            # 输出：只返回「要更新的字段」，不是整个 State
```

- Node 返回的是**局部更新**（partial update），不是完整 State。
- 返回 `{"messages": [response]}` 并不会覆盖历史，而是交给 Reducer 追加。
- 如果 Node 什么都不更新，返回 `{}` 或 `{"messages": []}`（你的 `_run_tool_group` 在没有本组调用时就返回 `{"messages": []}`）。

#### 补充 1-3：图是怎么跑起来的（superstep 机制）

LangGraph 的执行模型借鉴了 Pregel，按「超步（superstep）」一轮一轮推进：

```text
一个 superstep：
  1. 确定本步要运行的节点（被上一步的写入触发的节点）
  2. 同一步里的多个节点并行执行
  3. 本步所有节点的更新统一合并到 State（经过 Reducer）
  4. 保存一个 Checkpoint
  5. 没有可运行节点 → 结束；超过 recursion_limit → 抛 GraphRecursionError
```

用你的代码跑一次「搜索新闻」：

```text
step 0: 输入写入 messages
step 1: agent 运行       → 追加 AIMessage(tool_calls)
step 2: tools_search 运行 → 追加 ToolMessage
step 3: agent 运行       → 追加最终 AIMessage（无 tool_calls）→ 路由到 END
```

`recursion_limit` 限制的就是 superstep 的数量，不是工具调用次数。你的 `main()` 里设为 10，大约允许 4 到 5 轮「agent → 工具」循环。

#### 补充 1-4：`compile()` 做了什么

`g.compile(checkpointer=checkpointer)` 返回一个可执行的图对象（`CompiledStateGraph`）：

- 校验图结构（入口是否存在、节点名是否对得上等）。
- 绑定 Checkpointer，之后每个 superstep 都会保存状态。
- 返回的对象支持 `invoke / ainvoke / stream / astream` 等方法（见第 9 节）。

---

### 2. 条件路由

**定义：**

条件路由是根据当前 State 或节点执行结果，动态决定下一个执行节点的机制。

**目的：**

让工作流能够根据不同情况执行不同路径，而不是始终按照固定顺序执行。

**原理：**

条件路由通常通过一个判断函数实现：

```python
def route(state):
    if state["need_tool"]:
        return "tools"
    return "end"
```

然后将不同返回值映射到对应节点。

**实践：**

在 Agent 工作流中，模型返回工具调用请求时，流程进入工具节点；模型返回最终答案时，流程进入结束节点。

**局限与取舍：**

路由条件需要明确，避免分支过多导致流程难以维护。对于复杂路由，应注意状态字段是否完整、判断逻辑是否存在冲突。

#### 补充 2-1：你的 `route_after_agent()` 逐行解释

```python
def route_after_agent(state: MessagesState):
    last = state["messages"][-1]                       # ① 取最后一条消息（刚由 agent 产生的 AIMessage）
    tool_calls = getattr(last, "tool_calls", None)     # ② 读取模型发起的工具调用
    if not tool_calls:                                 # ③ 没有工具调用 → 模型已经给出最终回答
        return END
    groups_present = {TOOL_GROUP_MAP.get(c["name"], GROUP_SEARCH) for c in tool_calls}   # ④ 这些调用分属哪些组
    node_name = {GROUP_SEARCH: "tools_search", GROUP_REPORT: "tools_report"}
    return [Send(node_name[g], state) for g in groups_present]   # ⑤ 每个组发一个 Send，并行执行
```

路由函数可以返回三类值：

| 返回值 | 含义 |
|---|---|
| 节点名字符串 | 跳到该节点；若配置了 `path_map`，则先按映射表转换 |
| `END` | 结束 |
| `list[Send]` | 向一个或多个节点发送任务（动态并行分发），见第 8 节 |

你的代码返回的是 `END` 或 `list[Send]`。`Send` 自带目标节点名，所以 `add_conditional_edges` 里的 `path_map` 对它不起主要作用，更多是用来描述图的可能走向（也方便可视化）。

路由函数的约束：它应该是**纯判断函数**，只读 State，不要在里面修改状态或做耗时操作。

#### 补充 2-2：固定边 vs 条件边

```python
g.add_edge("tools_search", "agent")      # 固定边：tools_search 跑完一定去 agent
g.add_conditional_edges("agent", route_after_agent, {...})   # 条件边：agent 跑完由函数决定去向
```

注意你分别写了两条固定边：`tools_search → agent` 和 `tools_report → agent`。

- 分开写：**任意一个**工具节点完成就能触发 agent。如果这一轮只有搜索工具被调用，agent 在搜索完成后就会运行。
- 如果写成 `add_edge(["tools_search", "tools_report"], "agent")`：则要**等两个都完成**才触发 agent。那样当某一轮只触发了其中一个工具节点时，agent 就永远等不到另一个，流程会卡住。

所以这里分开写是正确的，面试时可以作为细节点提到。

---

### 3. Reducer 的作用

**定义：**

Reducer 是一种状态更新规则，用于决定节点返回的新数据如何与已有 State 合并。

**目的：**

当多个节点需要更新同一个状态字段时，明确规定数据应该如何合并，而不是简单覆盖。

**原理：**

例如，一个列表字段可以使用追加方式合并：

```python
def merge_messages(old, new):
    return old + new
```

如果 State 中的字段配置了 Reducer，节点更新该字段时会按照对应规则处理。

没有配置 Reducer 时，通常采用新的值覆盖旧值的方式。

**实践：**

在 Agent 场景中，消息列表需要保留历史对话，因此通常使用追加消息的更新方式，而不是直接丢弃之前的消息。

**局限与取舍：**

Reducer 需要保证合并逻辑符合业务预期。如果重复追加相同消息，可能造成状态膨胀或重复内容。

#### 补充 3-1：Reducer 怎么写在 State 里

```python
import operator
from typing import Annotated
from typing_extensions import TypedDict

class MyState(TypedDict):
    count: int                                   # 没有 Reducer：后写的覆盖先写的
    logs: Annotated[list[str], operator.add]     # 有 Reducer：列表相加（追加）
    messages: Annotated[list, add_messages]      # 消息专用 Reducer
```

规则：`Annotated[类型, reducer函数]`，reducer 接收 `(旧值, 新值)`，返回合并后的值。

#### 补充 3-2：`add_messages` 具体做了什么

`add_messages` 是 LangGraph 专为消息列表写的 Reducer，不是简单的 `old + new`：

1. **追加**：新消息追加到列表末尾。
2. **按 id 更新**：如果新消息的 `id` 与已有消息相同，则**替换**那条消息，而不是重复追加。
3. **自动补 id**：没有 `id` 的消息会被分配一个。
4. **删除**：传入 `RemoveMessage(id=...)` 可以从 State 中删除对应消息。
5. **格式兼容**：允许传 `("user", "你好")` 或 `{"role": "user", "content": "你好"}`，会自动转成消息对象。

所以你在 `ainvoke({"messages": [HumanMessage(content=q)]}, ...)` 传入的消息，是被追加到该 thread 已有的历史之后，而不是替换。

#### 补充 3-3：为什么你的项目离不开 Reducer

同一个 superstep 里，`tools_search` 和 `tools_report` 可能**同时**返回 `{"messages": [...]}`：

```text
tools_search → {"messages": [ToolMessage(A)]}
tools_report → {"messages": [ToolMessage(B)]}
                ↓ add_messages 合并
messages = [..., AIMessage, ToolMessage(A), ToolMessage(B)]
```

如果 `messages` 字段没有 Reducer，两个节点在同一步写同一个字段会产生冲突（`InvalidUpdateError`）。这就是并行节点 + Reducer 必须配合使用的原因。

另外要注意：`_shrink` 会新建 `ToolMessage` 副本，但它只用于送入 LLM，**不会写回 State**，所以不会触发「重复追加」。

---

### 4. ToolNode 如何执行工具？

**定义：**

ToolNode 是 LangGraph 提供的工具执行节点，可以根据模型产生的工具调用请求执行对应工具。

**目的：**

将模型的工具选择和实际工具执行连接起来，减少手动编写工具分发逻辑的工作。

**原理：**

典型流程：

1. 将工具注册到工具列表。
2. 使用工具列表绑定模型。
3. 模型生成结构化工具调用请求。
4. ToolNode 根据工具名称和参数执行对应工具。
5. 将工具执行结果写入消息状态。
6. 流程返回 Agent 节点继续处理。

**实践：**

结合项目代码，找到工具注册、模型绑定和 ToolNode 执行的位置，跟踪一次新闻检索工具的调用。

**局限与取舍：**

ToolNode 负责执行工具，但不代表工具本身一定可靠。工具的参数校验、权限控制、超时和业务异常仍需要合理处理。

#### 补充 4-1：项目里「注册 → 绑定 → 执行」三个位置

| 步骤 | 代码位置 |
|---|---|
| ① 注册工具 | `init_agent()`：`TOOLS = list(mcp_tools) + [request_daily_report]`，再 `_split_tools_by_group` 分组 |
| ② 绑定模型 | `get_chat_model(..., tools=TOOLS)`（内部应是 `bind_tools`，需对照 `llm_client.py` 确认） |
| ③ 执行工具 | `_run_tool_group()`：`ToolNode(group_tools).ainvoke(...)` |

#### 补充 4-2：ToolNode 内部做了什么

`ToolNode.ainvoke({"messages": [AIMessage(tool_calls=[...])]})`：

1. 读取**最后一条** AIMessage 的 `tool_calls`。
2. 按 `name` 在自己持有的工具列表里找到对应工具。
3. 对每个调用，用 `args` 执行 `tool.ainvoke(args)`；多个调用会并发执行。
4. 把每个结果包成 `ToolMessage(content=结果, tool_call_id=对应id, name=工具名)`。
5. 返回 `{"messages": [ToolMessage, ...]}`。

默认情况下，工具抛出的异常会被转成一条错误内容的 ToolMessage，而不是让整个图崩溃（具体行为随版本，需对照所装版本的文档）。

#### 补充 4-3：你为什么要重新构造一个 AIMessage

```python
node = ToolNode(group_tools)
trimmed = AIMessage(content="", tool_calls=calls)      # calls 只包含「本组」的调用
result = await asyncio.wait_for(node.ainvoke({"messages": [trimmed]}), timeout=timeout_seconds)
```

原因：模型一次可能同时发出搜索和日报两类调用，而 `ToolNode(group_tools)` 只持有本组工具。如果把原始 AIMessage 直接交给它，它会找不到另一组的工具，产生「不是有效工具」的错误。所以先按分组过滤出本组的 `calls`，再包成一条新的 AIMessage。

超时也是在这里统一加的：`asyncio.wait_for(..., timeout=30)`，超时后手动为每个调用构造一条 ToolMessage，保证 `tool_call_id` 都有对应的结果（见第 7 节的配对规则）。

---

### 5. LangGraph 与普通链式调用的区别

**定义：**

普通链式调用通常按照预先定义的顺序执行多个处理步骤。

LangGraph 则通过图结构组织节点，支持状态传递、条件路由、循环和持久化等能力。

**目的：**

当 Agent 需要动态选择工具、重复执行某些节点或根据状态改变流程时，图结构比固定链式调用更灵活。

**原理：**

链式调用：

```text
A → B → C → D
```

LangGraph：

```text
A → B
    ├── C → B
    └── D → END
```

LangGraph 可以根据条件在不同节点之间跳转。

**实践：**

AI 资讯项目使用 LangGraph 组织 Agent 的工具调用流程，模型根据用户问题选择不同工具，而不是固定执行所有工具。

**局限与取舍：**

LangGraph 适合有状态、需要动态路由的工作流。对于简单、固定的任务，普通函数调用或链式流程更简单。

#### 补充 5-1：对比表

| 维度 | 链式调用（如 LCEL 的 `a \| b \| c`） | LangGraph |
|---|---|---|
| 流程形态 | 单向，一次走完 | 可分支、可循环 |
| 状态 | 数据沿链传递，没有统一共享状态 | 有共享 State，节点读写 |
| 循环 | 不适合 | 天然支持（agent ↔ tools） |
| 并行 | 有限支持 | 同一 superstep 内多节点并行，`Send` 动态分发 |
| 持久化 | 需要自己实现 | Checkpointer 内置 |
| 人工介入 | 不方便 | 可在节点前后中断、恢复 |
| 适用场景 | 固定流程（Prompt → LLM → 解析） | 需要循环决策的 Agent |

你的 Agent 的核心特征是「模型决定是否继续调用工具，工具结果再回到模型」，这是一个**循环**，链式结构表达不了，所以用图。

---

### 6. 为什么你的项目使用单 Agent + Tool Calling？

**定义：**

单 Agent + Tool Calling 是由一个 Agent 负责理解用户请求、选择工具、处理结果，并生成最终答案的设计方式。

**目的：**

通过多个专业工具扩展单个 Agent 的能力，同时避免多 Agent 之间的任务分配和通信开销。

**原理：**

```text
用户问题
   ↓
单个 Agent
   ↓
理解意图、选择工具
   ↓
调用对应工具
   ↓
获取工具结果
   ↓
生成最终回答
```

**实践：**

AI 资讯项目中，Agent 可以选择：

- `search_news`：关键词检索新闻。
- `search_news_semantic`：语义检索新闻。
- `get_daily_report`：获取已有日报。
- `request_daily_report`：请求生成日报。

由一个 Agent 根据问题选择合适的工具。

**局限与取舍：**

单 Agent 架构简单，适合当前项目的工具规模和任务复杂度。随着任务复杂度增加，可能出现上下文过长、工具选择困难等问题。

多 Agent 可以拆分专业任务，但会增加通信、调度、状态管理和调试成本。当前项目没有必要为了使用多 Agent 而增加复杂度。

#### 补充 6-1：项目里的「单 Agent」其实是单 LLM 节点 + 多工具组

```text
一个 agent 节点（只有一个 LLM 在做决策）
   ├── tools_search 组：search_news（以及未列入映射表的工具，默认归此组）
   └── tools_report 组：get_daily_report、request_daily_report
```
分组的价值：不同工具的超时、重试策略可以不同（`GROUP_CONFIG`），并且同一轮里两类工具可以并行。

### 7. AIMessage.tool_calls 与 ToolMessage（补充）

**定义：**

- `AIMessage`：**模型产生的消息**。当模型想调用工具时，消息里会带 `tool_calls`。
- `ToolMessage`：**工具执行结果的消息**，必须通过 `tool_call_id` 对应到某次调用。

**目的：**

用结构化的方式表达「模型想做什么」和「做完得到了什么」，让模型在下一轮能准确读取每次调用的结果。

**原理：**

```python
AIMessage(
    content="",
    tool_calls=[
        {"name": "search_news", "args": {"keyword": "强化学习"}, "id": "call_abc", "type": "tool_call"},
    ],
)
ToolMessage(content="[新闻1, 新闻2]", tool_call_id="call_abc", name="search_news")
```

| 对比项 | AIMessage.tool_calls | ToolMessage |
|---|---|---|
| 谁产生 | LLM | ToolNode / 你的代码 |
| 含义 | 请求：我想调用某工具 | 结果：该工具返回了什么 |
| 关键字段 | `name`、`args`、`id` | `content`、`tool_call_id`、`name` |
| 作用 | 驱动路由（有 tool_calls → 进工具节点） | 供 LLM 下一轮读取 |

**配对规则（重要）：** 每个 `tool_calls[i].id` 都必须有一条 `tool_call_id` 相同的 ToolMessage，否则多数模型 API 会报错。这就是你的超时分支里要为**每一个** `calls` 构造 ToolMessage 的原因。

**一次完整的消息序列：**

```text
HumanMessage("给我强化学习相关新闻")
AIMessage(tool_calls=[search_news(keyword="强化学习") id=call_1])
ToolMessage(tool_call_id=call_1, content="...新闻列表...")
AIMessage("以下是强化学习相关新闻：...")        ← 无 tool_calls，路由到 END
```

**实践：**

`route_after_agent` 通过 `getattr(last, "tool_calls", None)` 判断是否继续；`_run_tool_group` 为每个调用产出 ToolMessage。

**局限与取舍：**

- 模型可能一次发出多个调用，也可能参数不合法，工具层仍需校验。
- 如果一次运行被中途打断，Checkpoint 里可能留下「有 tool_calls 但没有对应 ToolMessage」的悬空调用，下一次在同一 thread 上提问时可能被模型 API 拒绝，需要在送入 LLM 前补占位结果。

### 8. Send：并行分发工具组（补充）

**定义：**

`Send(node, arg)` 表示「向某个节点发送一份输入，让它执行一次」。条件路由函数返回 `Send` 列表时，LangGraph 会在**同一个 superstep** 内并行运行这些节点。

**目的：**

当下一步要运行的节点数量、或各节点的输入是动态决定的（例如 map-reduce），固定边无法表达，需要 `Send`。

**原理：**

```python
return [Send("tools_search", state), Send("tools_report", state)]
```

- 第一个参数是**目标节点名**。
- 第二个参数是**该节点本次的输入**（你传的是完整 `state`，也可以只传子集）。
- **多个 `Send` 并行执行**，各节点的返回值在 superstep 结束时经 Reducer 合并。

在你的代码里：

```text
agent 产生 [search_news(...), get_daily_report(...)]
        ↓ route_after_agent 按分组
groups_present = {search, report}
        ↓
[Send("tools_search", state), Send("tools_report", state)]    ← 并行
        ↓ 各自过滤出本组的 calls 执行
两个 ToolMessage 经 add_messages 合并 → 回到 agent
```
如果这一轮只有搜索调用，就只会产生一个 `Send`，`tools_report` 不会运行。

**实践：**

同一组内的多个调用（比如一次发出两个 `search_news`）不是由 `Send` 并行的，而是由 `ToolNode` 在组内并发执行。

**局限与取舍：**

- 并行节点同时写同一字段必须有 Reducer。
- 并行会让日志顺序变得不直观，调试时要靠 `tool_call_id` 对应。
- 把整个 `state` 传给每个节点比较省事，但节点拿到了不需要的数据；调用量大时可以只传必要字段。

---

### 9. invoke() 与 ainvoke()（补充）

**定义：**

- `invoke()`：**同步调用**，调用线程会阻塞直到图运行结束。
- `ainvoke()`：**异步调用**，返回协程，需要 `await`，运行期间事件循环可以处理其他任务。
- **同类方法还有 `stream() / astream()`（逐步输出中间结果）和 `batch() / abatch()`（批量）**。

**目的：**

Agent 的主要耗时在** LLM 请求和工具调用**这类 I/O 上。异步调用可以在等待 I/O 时让出事件循环，让同一进程同时处理多个用户请求。

**原理与实践（对应你的代码）：**

| 位置 | 用法 | 原因 |
|---|---|---|
| `agent_node` 是 `async def` | `await agent_llm.ainvoke(...)` | 节点里用异步调用 LLM |
| `_run_tool_group` | `await node.ainvoke(...)`、`asyncio.wait_for(...)` | 异步执行工具并加超时 |
| `main()` | `await app_instance.ainvoke(...)` | 入口也必须是异步 |
| `AsyncSqliteSaver` | 只提供异步接口 | 因此整个图只能用 `ainvoke / astream` |
| `trigger_report_generation` | `asyncio.to_thread(_guarded)` | `daily_flow` 是同步的耗时任务，丢进线程，避免阻塞事件循环 |

一个常见错误：在 `async def` 的节点里直接调用同步的耗时函数（如 `daily_flow()`），会卡死事件循环，所有请求一起变慢。应该用 `asyncio.to_thread(...)` 或换成异步实现。

另外，如果图里的节点都是 `async def`，只能用 `ainvoke`；用同步的 `invoke` 会报错。

**局限与取舍：**

异步代码调试更难（任务取消、异常传播、上下文），也要警惕「在异步里混用阻塞调用」。简单脚本用同步版本更直观。

---

### 10. 上下文控制：trim_messages 与 _shrink（补充）

**定义：**

- `trim_messages`：按规则裁剪消息列表，只保留最近的一部分。
- `_shrink`（你自己写的）：把历史里过长的 ToolMessage 内容截断。

**目的：**

`messages` 会随对话不断增长，直接全部送给 LLM 会导致 Token 增多、变慢、变贵，甚至超出上下文窗口。

**原理：**

```python
msgs = trim_messages(
    state["messages"],
    strategy="last",          # 保留最后的消息
    max_tokens=MAX_HISTORY_MSGS,   # 16
    token_counter=len,        # 用「消息条数」当计数器，每条消息算 1
    start_on="human",         # 裁剪后的第一条必须是 HumanMessage
    include_system=False,
)
```

- `token_counter=len` 意味着这里按「条数」裁剪，保留最近 16 条消息，而不是按真实 Token 数。
- `start_on="human"` 保证裁剪后不会以孤立的 ToolMessage 或 AIMessage 开头（工具结果脱离了它对应的调用会让模型困惑，甚至报错）。
- `_shrink` 之后工具结果最多保留 `MAX_TOOL_CHARS = 3600` 个字符，超出的加上「…(已截断)」。

两层配合：`trim_messages` 控制**条数**，`_shrink` 控制**单条长度**。

```python
response = await agent_llm.ainvoke([system] + _shrink(msgs))
```

**实践中的关键点：**

1. 这两个操作只影响**送入 LLM 的副本**，`state["messages"]` 本身没有被改动，Checkpoint 里依然保存完整历史。所以数据库里的消息会持续增长，需要另外做清理（`RemoveMessage`、摘要等）。
2. System Prompt 不放在 State 里，每次调用时用 `build_agent_system_prompt(today)` 现场拼接，所以裁剪不会丢掉它。
3. 兜底分支 `msgs = state["messages"][-1:]`：当本轮消息太多、被全部裁掉时只保留最后一条。但最后一条很可能是 ToolMessage，会变成孤立的工具结果，存在被模型 API 拒绝的风险（建议改为保留整个本轮消息）。

**局限与取舍：**

- 按条数裁剪简单，但不精确：一条很长的消息和一条很短的消息算同样大小。
- 直接丢弃早期消息会丢掉早期信息。需要长期上下文时可以引入摘要，但会增加复杂度和一次额外的 LLM 调用。

---

### 11. Checkpointer、Thread ID、Checkpoint（原 Day 10 内容，完整保留）

**定义：**

- Checkpointer：LangGraph 提供的状态保存机制，用于在工作流执行过程中保存状态。
- Thread ID：用于标识一个独立的执行会话。
- Checkpoint：某个执行时刻保存下来的状态快照。

**目的：**

让 Agent 能够保存执行过程中的状态，支持多轮对话、执行恢复和中断后继续运行。

**原理：**

LangGraph 执行过程中会产生 State，Checkpointer 可以将 State 保存为 Checkpoint。

不同 Thread ID 对应不同的执行会话，通过 Thread ID 可以找到对应的历史状态。

基本流程：

```text
用户请求
   ↓
传入 Thread ID
   ↓
LangGraph 执行
   ↓
产生新的 State
   ↓
Checkpointer 保存 Checkpoint
   ↓
下次使用相同 Thread ID
   ↓
恢复之前的状态
```

**实践：**

可以使用 MemorySaver 编写最小 Demo：

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

graph = builder.compile(
    checkpointer=checkpointer
)

config = {
    "configurable": {
        "thread_id": "user_001"
    }
}

result = graph.invoke(
    {"messages": []},
    config=config
)
```

使用相同的 Thread ID 再次调用，可以继续使用该会话保存的状态。

**局限与取舍：**

InMemorySaver 只适合内存中的临时状态保存，程序重启后数据会丢失。

生产环境通常需要使用持久化存储，例如数据库 Checkpointer。

Checkpointer 会增加状态管理成本，还需要考虑数据清理、会话隔离和敏感信息保护。

#### 补充 11-1：你的项目里的 AsyncSqliteSaver

```python
raw = (os.getenv("CHAT_MEMORY_DB_PATH") or "").strip()
db_path = os.path.expanduser(raw)
os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)   # 目录不存在时先创建
conn = await aiosqlite.connect(db_path)                                 # 异步 SQLite 连接
saver = AsyncSqliteSaver(conn)
await saver.setup()                                                      # 建表
app = build_graph(saver)                                                 # compile(checkpointer=saver)
```

| 对象 | 说明 |
|---|---|
| `InMemorySaver` | 存在进程内存里，重启即丢，适合 Demo 和测试 |
| `AsyncSqliteSaver` | 存在 SQLite 文件里，进程重启后还在，只提供异步接口 |
| 数据库类 Checkpointer（如 Postgres） | 多进程、多机器部署时更合适 |

#### 补充 11-2：保存和恢复是怎么发生的

1. 调用 `ainvoke(input, config={"configurable": {"thread_id": "u1"}})`。
2. LangGraph 用 `thread_id` 找到该线程最新的 Checkpoint，恢复 State（即历史 `messages`）。
3. 把本次输入通过 Reducer 合并进去，开始运行。
4. **每个 superstep 结束**都会保存一个新的 Checkpoint（记录当时的 State、下一步要运行的节点等），Checkpoint 之间通过父子关系串成历史。
5. 下次用同一个 `thread_id` 就从最新 Checkpoint 继续。

保存的内容主要是 State 快照与元数据（具体表结构以所装版本为准）。也因为有历史 Checkpoint，所以可以查看某个线程的状态、回溯到更早的状态（`aget_state`、`aget_state_history`）。


### 12. 状态持久化和多轮对话（原 Day 10 内容，完整保留）

**定义：**

状态持久化是将 Agent 执行过程中的状态保存到存储介质，使其在后续调用中能够恢复。

多轮对话是指系统能够保留之前的对话上下文，并根据历史信息理解用户后续的问题。

**目的：**

让 Agent 不必每次都从零开始处理请求，可以结合历史对话理解上下文。

**原理：**
例如：
```text
第一轮：
用户：查询今天的大模型新闻
   ↓
Agent 检索新闻
   ↓
保存对话状态

第二轮：
用户：其中有哪些和 Agent 有关？
   ↓
使用相同 Thread ID
   ↓
读取历史对话状态
   ↓
结合上一轮结果继续回答
```
LangGraph 通过 Checkpointer 保存状态，并根据 Thread ID 恢复对应会话。

**实践：**

可以编写一个多轮对话 Demo：

1. 第一轮输入一个问题。
2. 使用固定 Thread ID 执行 Graph。
3. 第二轮输入一个依赖上下文的问题。
4. 使用相同 Thread ID 再次执行。
5. 更换 Thread ID，观察对话是否隔离。

AI 资讯项目可以使用这种方式实现连续对话，但需要先确认项目是否实际配置了 Checkpointer。

**局限与取舍：**

状态持久化不等于长期记忆。它主要保存工作流执行状态，不代表 Agent 自动具备长期知识记忆能力。

对话历史过长也会增加 Token 消耗，需要考虑历史消息裁剪、摘要和上下文管理。

#### 补充 12-1：多轮对话在你的项目里如何串起来

```text
第 1 轮：ainvoke({"messages":[Human(q1)]}, thread_id="u1")
          State.messages = [Human(q1), AI(tool_calls), Tool, AI(answer1)]   → 存入 Checkpoint

第 2 轮：ainvoke({"messages":[Human(q2)]}, thread_id="u1")
          恢复 → [Human(q1), AI, Tool, AI(answer1)]
          add_messages 追加 → [..., Human(q2)]
          agent_node 里 trim_messages 取最近 16 条送入 LLM
```

多轮对话涉及三件事，分别对应三个机制：

| 需求 | 机制 |
|---|---|
| 记住之前说过的话 | Checkpointer + `thread_id` + `add_messages` |
| 不同用户互不干扰 | 不同的 `thread_id` |
| 历史太长不爆上下文 | `trim_messages` + `_shrink` |

#### 补充 12-2：持久化 ≠ 长期记忆

| 对比 | 状态持久化（Checkpointer） | 长期记忆 |
|---|---|---|
| 保存什么 | 某个线程的执行状态与对话历史 | 跨会话的用户偏好、事实等知识 |
| 作用范围 | 单个 `thread_id` | 可以跨线程、跨会话 |
| 谁来决定存什么 | 框架自动保存 | 需要自己设计（提取、写入、检索） |
| LangGraph 对应能力 | Checkpointer | Store（跨线程的键值存储）等 |

你的项目目前只用了前者。

---

### 13. 完整拆解 build_graph()（补充）

```python
def build_graph(checkpointer):
    g = StateGraph(MessagesState)
    g.add_node("agent", agent_node)
    g.add_node("tools_search", tools_search_node, retry_policy=GROUP_CONFIG[GROUP_SEARCH]["retry"])
    g.add_node("tools_report", tools_report_node, retry_policy=GROUP_CONFIG[GROUP_REPORT]["retry"])
    g.set_entry_point("agent")
    g.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools_search": "tools_search", "tools_report": "tools_report", END: END},
    )
    g.add_edge("tools_search", "agent")
    g.add_edge("tools_report", "agent")
    return g.compile(checkpointer=checkpointer)
```

| 代码 | 作用 |
|---|---|
| `StateGraph(MessagesState)` | 创建图构建器，State 里只有带 `add_messages` Reducer 的 `messages` |
| `add_node("agent", agent_node)` | 注册 LLM 决策节点 |
| `add_node("tools_search", ..., retry_policy=...)` | 注册搜索工具节点，并设置节点级重试策略 |
| `add_node("tools_report", ..., retry_policy=...)` | 注册日报工具节点 |
| `set_entry_point("agent")` | 从 agent 开始 |
| `add_conditional_edges("agent", route_after_agent, path_map)` | agent 之后由路由函数决定去向 |
| `add_edge("tools_*", "agent")` | 工具跑完回到 agent，形成循环 |
| `compile(checkpointer=...)` | 编译并绑定 Checkpointer |

图的拓扑：

```text
START ─▶ agent ─┬─▶ END
        ▲       ├─▶ tools_search ─┐
        │       └─▶ tools_report ─┤
        └─────────────────────────┘
```

#### ❗❗ 关于 `retry_policy` 的一个重要细节

`RetryPolicy` 只会在**节点抛出异常**时触发重试。而你的 `_run_tool_group` 把超时捕获后转成了一条正常返回的 ToolMessage，`ToolNode` 默认也会把工具异常转成错误 ToolMessage。这意味着正常情况下节点不会抛异常，`RetryPolicy` 很可能不会生效。

所以回答面试官时，不要说「我配置了搜索工具重试 2 次所以很稳」，更准确的说法是「配置了节点级重试，但超时和工具错误被我转成了 ToolMessage，要让重试真正生效，需要在 `_run_tool_group` 内部自己写重试循环」。

---

### 14. 完整执行追踪：一次提问（补充）

#### 场景 A：「给我强化学习相关新闻」

| 步骤 | 节点 | 做了什么 | messages 变化 |
|---|---|---|---|
| 0 | 入口 | `ainvoke` 传入 HumanMessage，按 `thread_id` 恢复历史 | `[..历史.., Human]` |
| 1 | agent | 拼 System Prompt、裁剪历史、调用 LLM | 追加 `AI(tool_calls=[search_news])` |
| 2 | 路由 | 有 tool_calls → 分组 → `[Send("tools_search")]` | 不变 |
| 3 | tools_search | 过滤出本组调用，`ToolNode` 执行，30 秒超时保护 | 追加 `ToolMessage` |
| 4 | agent | 读取工具结果，生成回答 | 追加 `AI(answer)` |
| 5 | 路由 | 无 tool_calls → END | 不变 |

每个 superstep 结束保存一次 Checkpoint。

#### 场景 B：「给我今天的日报」，且日报尚未生成

```text
agent  → AI(tool_calls=[get_daily_report(date)])
tools_report → ToolMessage("日报不存在")
agent  → AI(tool_calls=[request_daily_report(date)])
tools_report → 本地工具 request_daily_report
                ├─ 日期格式校验
                ├─ 对该日期的锁 acquire(blocking=False)；拿不到 → 返回「正在生成中」
                ├─ asyncio.to_thread 在后台线程跑 daily_flow
                └─ 立即返回「已启动…请稍后查询」
agent  → AI("日报正在生成，请几分钟后再来查询")  → END
```

这里的设计要点：

- **按日期加锁**（`_GEN_LOCKS`）防止重复触发生成。
- **后台线程**：耗时任务不阻塞事件循环，也不阻塞这次对话。
- **BACKGROUND_TASKS 集合**保存任务引用，防止任务被垃圾回收。
- 工具只负责「触发」，不等待结果，所以 Agent 回复的是「已启动」而不是日报内容。

---

### 15. 最小 LangGraph Demo（对应实践任务第 3 条）

不需要 API Key。用一个规则函数模拟「LLM 决策」，其余部分（State、条件路由、ToolNode、Checkpointer、多轮、线程隔离）都是真实的 LangGraph 机制。

```python
# demo_langgraph.py
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver


@tool
def search_news(keyword: str) -> str:
    """根据关键词搜索新闻。"""
    return f"找到 2 条关于「{keyword}」的新闻：①{keyword}新进展 ②{keyword}应用案例"


tools = [search_news]


def agent(state: MessagesState):
    """模拟 LLM：看最后一条消息决定下一步。"""
    last = state["messages"][-1]

    # 情况 1：用户刚提问
    if isinstance(last, HumanMessage):
        if "新闻" in last.content:                      # 判断：需要工具
            keyword = last.content.replace("给我", "").replace("相关新闻", "").replace("新闻", "") or "AI"
            return {"messages": [AIMessage(
                content="",
                tool_calls=[{"name": "search_news", "args": {"keyword": keyword}, "id": "call_1"}],
            )]}
        return {"messages": [AIMessage(content=f"（历史共 {len(state['messages'])} 条消息）我没有调用工具，直接回答。")]}

    # 情况 2：刚拿到工具结果
    if isinstance(last, ToolMessage):
        return {"messages": [AIMessage(content=f"根据检索结果：{last.content}")]}


def route(state: MessagesState):
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


g = StateGraph(MessagesState)
g.add_node("agent", agent)
g.add_node("tools", ToolNode(tools))
g.add_edge(START, "agent")
g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
g.add_edge("tools", "agent")
app = g.compile(checkpointer=InMemorySaver())


def ask(q, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    result = app.invoke({"messages": [HumanMessage(content=q)]}, config=cfg)
    print(f"[{thread_id}] {q}\n   → {result['messages'][-1].content}")
    print(f"   当前该线程消息数：{len(result['messages'])}")


if __name__ == "__main__":
    ask("给我强化学习相关新闻", "user_001")     # 走工具分支：Human → AI(tool_calls) → Tool → AI
    ask("谢谢", "user_001")                    # 同一线程：消息数继续增长，说明历史被恢复
    ask("谢谢", "user_002")                    # 新线程：消息数从头开始，说明线程隔离

    # 查看执行过程：每个节点的更新
    cfg = {"configurable": {"thread_id": "user_003"}}
    for step in app.stream({"messages": [HumanMessage(content="给我大模型新闻")]}, cfg, stream_mode="updates"):
        print(step)
```

预期现象（用来自测）：

1. 第一次提问经过 `agent → tools → agent`，消息数为 4。
2. 第二次同线程提问，消息数继续增加，且回答里的「历史共 N 条」大于 1。
3. 换线程后消息数重新从 2 开始。
4. `stream_mode="updates"` 会依次打印 `agent`、`tools`、`agent` 三个节点的更新，对应前面说的 superstep。

动手改造建议（逐步加难度）：

- 把 `InMemorySaver` 换成 `AsyncSqliteSaver`，节点改成 `async def`，入口改成 `ainvoke`，体会同步和异步的区别。
- 增加第二个工具 `get_daily_report`，并改写 `route` 返回 `Send`，体会并行分发。
- 把 `agent` 换成真实 LLM：`llm.bind_tools(tools)`（见 Day 10）。

---

## 二、实践任务

- [ ] 找到项目中 StateGraph 的定义。（答案：`build_graph()`，见第 13 节）
- [ ] 跟踪 Node、Edge 和条件路由的执行。（答案：见第 14 节的两个场景）
- [ ] 自己写一个最小的 LangGraph 流程：用户输入 → 判断 → 工具调用 → 返回结果。（见第 15 节，并自己改写一遍，不要只复制）
- [ ] 检查项目是否真正使用了 Checkpoint，不要把了解的功能说成已经实现。（核对方法见第 11 节补充 11-3）
- [ ] 在 `agent_node` 里加一行打印，确认每次送入 LLM 的消息数是否真的被限制在 16 条以内。
- [ ] 用同一个 `thread_id` 连续提问两次，再换 `thread_id` 提问一次，验证记忆与隔离。

---

## 三、学习复盘

**今天还没搞懂的内容：**

- State 在多个 Node 之间如何传递和更新？多个 Node 更新同一个字段时如何处理？
- 条件路由如何决定下一步执行哪个 Node？
- Checkpointer 如何根据 Thread ID 保存和恢复状态？状态持久化与长期记忆有什么区别？

**需要面试前回顾的内容：**

- StateGraph、State、Node、Edge 分别是什么？它们之间是什么关系？
- Reducer 有什么作用？为什么需要它？
- LangGraph 相比普通链式调用有什么优势？项目为什么选择单 Agent + Tool Calling？
- Checkpointer、Thread ID、Checkpoint 分别是什么？

### 对上面「没搞懂」问题的回答（补充）

**1. State 在多个 Node 之间如何传递和更新？多个 Node 更新同一个字段时如何处理？**

State 是整个图共享的一份数据。每个 Node 读取当前 State，返回局部更新；框架在 superstep 结束时，用字段上绑定的 Reducer 把更新合并进 State。同一步多个 Node 写同一个字段时，有 Reducer 就按规则合并（如 `add_messages` 追加），没有 Reducer 则会冲突报错（顺序执行时则是后写覆盖先写）。

**2. 条件路由如何决定下一步执行哪个 Node？**

`add_conditional_edges` 在源节点执行后调用路由函数，函数读取 State 返回下一步：节点名、`END` 或 `Send` 列表。你的 `route_after_agent` 根据最后一条 AIMessage 有没有 `tool_calls` 来判断，并用 `Send` 按工具分组并行分发。

**3. Checkpointer 如何根据 Thread ID 保存和恢复状态？**

每个 superstep 结束保存一个 Checkpoint，归属到 `config["configurable"]["thread_id"]` 对应的线程。下次同一个 `thread_id` 调用时取最新 Checkpoint 恢复 State，再合并新输入继续执行。

**4. 状态持久化与长期记忆有什么区别？**

持久化保存的是单个线程的执行状态和对话历史；长期记忆是跨会话的知识，需要另外设计存储和检索。

---

## ❗❗ 四、项目代码中值得注意的细节（面试可主动提，也是后续优化点）

1. **Checkpointer 静默降级**：初始化失败只打印日志并退化为无记忆模式，线上要有监控，避免以为有记忆实际没有。
2. **`main()` 的 `thread_id` 每次不同**：这个入口不会体现多轮记忆。
3. **历史只裁剪不清理**：`trim_messages` 只影响送入 LLM 的副本，数据库里的 `messages` 会一直增长。
4. **`RetryPolicy` 基本不会触发**：超时和工具错误都被转成了 ToolMessage（见第 13 节）。
5. **`trim_messages` 兜底分支**：`state["messages"][-1:]` 可能留下孤立的 ToolMessage。
6. **悬空 tool_calls**：运行被中断后，同一线程下一次提问前需要补占位 ToolMessage。
7. **`recursion_limit` 只在 `main()` 里设置**：FastAPI 入口也要传，并捕获 `GraphRecursionError`。
8. **aiosqlite 连接没有在 `close_agent()` 里关闭**：应保存 `conn` 并在关闭时 `await conn.close()`。
9. **`search_news_semantic` 未写入 `TOOL_GROUP_MAP`**：目前靠默认值归入搜索组，建议显式声明。
10. **没有循环保护**：模型反复调用工具时只靠 `recursion_limit` 兜底，缺少业务层的轮数、重复调用和熔断控制（上一轮给出的 `agent_graph.py` 里有一个参考实现）。

---

## 五、面试高频问答（精简版）

**Q1：LangGraph 是什么？为什么不用普通链？**
答：LangGraph 是构建**有状态、可循环**的 Agent 工作流的框架，用 State、Node、Edge 描述流程。Agent 的核心是「模型决策 → 调工具 → 结果回到模型」的循环，链式结构表达不了，所以用图。

**Q2：State 和 Reducer 是什么关系？**
答：**State 是共享数据**，Reducer 决定**节点返回的更新怎样合并进 State**。`messages` 字段绑定了 `add_messages`，所以节点返回的消息是追加而不是覆盖，并行节点同时写也不会冲突。

**Q3：你怎么实现条件路由和并行工具执行？**
答：`route_after_agent` 看最后一条 AIMessage 有没有 `tool_calls`；没有就 END，有就按工具分组**返回 `Send` 列表**，搜索组和日报组在同一个 superstep 并行执行，结果经 `add_messages` 合并后回到 agent。

**Q4：AIMessage.tool_calls 和 ToolMessage 是什么关系？**
答：前者是模型发出的调用请求，后者是执行结果，通过 `tool_call_id` 一一配对，缺少配对模型 API 会报错。所以我在超时分支也为每个调用构造了 ToolMessage。

**Q5：怎么控制上下文长度？**
答：两层。`trim_messages` 只送最近 16 条，并要求从 HumanMessage 开始；`_shrink` 把历史中超过 3600 字符的工具结果截断。它们只处理送入 LLM 的副本，Checkpoint 里仍是完整历史。

**Q6：多轮对话怎么实现？**
答：用 `AsyncSqliteSaver` 做 Checkpointer，调用时传 `thread_id`。每个 superstep 保存 Checkpoint，下次同一 `thread_id` 恢复历史再追加新输入。不同 `thread_id` 之间互相隔离。我也核对过：如果没配置 `CHAT_MEMORY_DB_PATH` 会退化为无记忆模式。

**Q7：为什么用 `ainvoke`？**
答：Agent 主要耗时在 LLM 和工具的 I/O，异步可以在等待时处理其他请求；而且 `AsyncSqliteSaver` 只有异步接口。同步的耗时任务（如 `daily_flow`）用 `asyncio.to_thread` 放到线程里，避免阻塞事件循环。

**Q8：这个设计有什么不足？**
答：（参考第四节）没有业务层的循环保护、`RetryPolicy` 实际不生效、历史只裁剪不清理、Checkpointer 失败时静默降级等。这些我知道，也有对应的改进方案。
