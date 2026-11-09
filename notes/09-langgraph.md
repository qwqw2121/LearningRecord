# Day 9｜LangGraph

## 技术面试回答结构

1. 定义：它是什么？用自己的话解释概念
2. 目的：为什么需要它？理解它解决什么问题
3. 原理：它内部怎么工作？理解核心机制
4. 实践：我在项目中怎么使用？
5. 取舍：有什么局限，为什么选择它？

## 一、学习内容与记录

### 1. StateGraph、State、Node、Edge

**定义：**

LangGraph 是一个用于构建**有状态、多步骤** Agent 工作流的**框架**。

- StateGraph：定义整个图结构。
- State：保存工作流执行过程中的**共享状态**。
- Node：**执行具体任务的节点**，通常是一个函数。
- Edge：定义节点之间的执行关系。

**目的：**

将复杂的 Agent 执行流程拆分成**多个节点**，通过**状态传递和边连接**控制执行过程。

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
Node 接收当前 State，执行任务后返回**状态更新**。Edge 决定下一个执行节点。

**实践：**

在 AI 资讯项目中，找到 LangGraph 工作流的构建代码，理解 State 保存了哪些信息，以及 Agent 节点如何调用工具。
state: MessagesState

**局限与取舍：**

LangGraph 提供了较强的**流程控制能力**，但也增加了代码结构和状态管理复杂度。简单的单次模型调用不一定需要使用 LangGraph。

### 2. 条件路由

**定义：**

条件路由是根据**当前 State 或节点执行结果**，动态决定下一个执行节点的机制。

**目的：**

让工作流能够根据**不同情况执行不同路径**，而不是始终按照固定顺序执行。

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
```Python
def route_after_agent(state: MessagesState):
          last = state["messages"][-1]
          tool_calls = getattr(last, "tool_calls", None)
          if not tool_calls:
                    return END
          groups_present = {TOOL_GROUP_MAP.get(c["name"], GROUP_SEARCH) for c in tool_calls}
          node_name = {GROUP_SEARCH: "tools_search", GROUP_REPORT: "tools_report"}
          return [Send(node_name[g], state) for g in groups_present]
```
我的项目使用 route_after_agent 实现条件路由。

主要逻辑：
1. 获取最后一条 AIMessage。
2. 检查其中是否存在 tool_calls。
3. 如果不存在，返回 END。
4. 如果存在，根据工具名称将调用分组。
5. 使用 Send 将任务动态分发到对应的工具 Node。

**局限与取舍：**

路由条件需要明确，避免分支过多导致流程难以维护。对于复杂路由，应注意状态字段是否完整、判断逻辑是否存在冲突。

### 3. Reducer 的作用

**定义：**

Reducer 是一种**状态更新规则**，用于**决定节点返回的新数据如何与已有 State 合并**。

**目的：**

当多个节点需要更新同一个状态字段时，明确规定数据应该如何合并，而不是简单覆盖。

**原理：**

例如，一个列表字段可以使用追加方式合并：

```python
def merge_messages(old, new):
    return old + new
```

如果 State 中的字段配置了 Reducer，节点更新该字段时会按照对应规则处理。

没有配置 Reducer 时，通常采用**新的值覆盖旧值**的方式。

**实践：**

在 Agent 场景中，消息列表需要保留历史对话，因此通常使用追加消息的更新方式，而不是直接丢弃之前的消息。

**局限与取舍：**

Reducer 需要保证合并逻辑符合业务预期。如果重复追加相同消息，可能造成状态膨胀或重复内容。

### 4. ToolNode 如何执行工具？

**定义：**

ToolNode 是 LangGraph 提供的**工具执行节点**，可以根据模型产生的**工具调用请求执行对应工具**。

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

### 5. LangGraph 与普通链式调用的区别

**定义：**

普通链式调用通常按照**预先定义的顺序**执行多个处理步骤。

LangGraph 则通过**图结构组织节点**，支持**状态传递、条件路由、循环和持久化**等能力。

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

LangGraph 可以**根据条件在不同节点之间跳转**。

**实践：**

AI 资讯项目使用 LangGraph 组织 Agent 的工具调用流程，模型根据用户问题选择不同工具，而不是固定执行所有工具。

**局限与取舍：**

LangGraph 适合有状态、需要动态路由的工作流。对于简单、固定的任务，普通函数调用或链式流程更简单。

### 6. 为什么你的项目使用单 Agent + Tool Calling？

**定义：**

单 Agent + Tool Calling 是由一个 Agent 负责理解用户请求、选择工具、处理结果，并生成最终答案的设计方式。

**目的：**

通过多个专业工具扩展单个 Agent 的能力，同时避免**多 Agent 之间的任务分配和通信开销**。

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

多 Agent 可以拆分**专业任务**，但会增加通信、调度、状态管理和调试成本。当前项目没有必要为了使用多 Agent 而增加复杂度。

## 二、实践任务

- [ ] 找到项目中 StateGraph 的定义。
- [ ] 跟踪 Node、Edge 和条件路由的执行。
- [ ] 自己写一个最小的 LangGraph 流程：用户输入 → 判断 → 工具调用 → 返回结果。

## 三、学习复盘

**今天还没搞懂的内容：**

- State 在多个 Node 之间如何传递和更新？多个 Node 更新同一个字段时如何处理？
  State 是整个 LangGraph 工作流共享的状态，负责在不同 Node 之间传递数据。
  每个 Node 接收当前 State，读取自己需要的数据，然后返回一个字典，表示本次需要更新的字段。LangGraph 会根据 State 中定义的 Reducer，将 Node 返回的更新合并到原有 State 中，再传递给后续 Node。
  多个 Node 更新同一个字段时：由该字段定义的 **Reducer **决定如何合并更新。

- 条件路由如何决定下一步执行哪个 Node？
  条件路由是根据当前 State 中的数据，动态决定下一步执行哪个 Node。实现上，通常通过一个路由函数读取 State，判断当前状态，然后返回目标 Node 的名称，或者**返回 Send 对象进行动态任务分发**。
执行逻辑：
  - 如果模型返回了 Tool Call，就进入 tools Node。
  - 如果模型没有返回 Tool Call，说明模型已经生成最终回答，结束流程。
  
**需要面试前回顾的内容：**

- StateGraph、State、Node、Edge 分别是什么？它们之间是什么关系？
- Reducer 有什么作用？为什么需要它？
- LangGraph 相比普通链式调用有什么优势？项目为什么选择单 Agent + Tool Calling？

- StateGraph、State、Node、Edge 分别是什么？它们之间是什么关系？
 - StateGraph 是整个工作流的框架。
 - State 是工作流运行过程中共享的数据。
 - Node 是具体执行任务的函数。
 - Edge 决定 Node 之间如何连接和流转。

- Reducer 有什么作用？为什么需要它？
   Reducer 是用于定义 State 字段更新和合并规则的机制。
   Node 执行后会返回部分 State 更新，**Reducer 决定这些更新如何与原有 State 合并**。
   常见情况：
   1. 没有 Reducer：通常使用新值覆盖旧值。
   2. 定义了 Reducer：按照指定规则合并新旧值。
   3. 多个并行 Node 更新同一个字段：通过 Reducer 处理多个更新，避免简单覆盖造成数据丢失或并发更新冲突。
我的项目直接使用 LangGraph 提供的 MessagesState。其中 messages 字段**使用 add_messages Reducer，负责合并 AIMessage、HumanMessage 和 ToolMessage**。这样 Agent 的消息和工具执行结果就能持续保存在 State 中，供下一轮 Agent 推理使用。

- LangGraph 相比普通链式调用有什么优势？
  普通链式调用通常按照固定顺序执行,适合简单、线性的任务。
  LangGraph 则使用图结构组织工作流，可以定义多个 Node、条件路由、循环执行和状态更新，更适合复杂的 Agent 应用。

- 项目为什么选择单 Agent + Tool Calling？
  最初项目采用 Supervisor 多 Agent 架构，将任务拆分为多个 Agent，但实际开发中发现部分 Agent 的职责边界不够清晰，路由逻辑比较复杂，而且多次模型调用增加了系统开销。

   后来分析项目需求，发现核心任务主要是新闻检索、日报读取和日报生成，这些任务可以通过工具完成，不需要多个 Agent 分别进行复杂推理。

   因此，我将架构调整为单 Agent + Tool Calling：
   - Agent：负责理解用户意图、决定调用什么工具、整合工具结果。
   - Tools：负责具体业务操作，例如新闻检索、日报读取和日报生成。
   - LangGraph：负责管理 Agent 和工具之间的执行流程。
   这种架构职责更清晰，减少了不必要的 Agent 协作和模型调用开销，也降低了系统复杂度
单 Agent + Tool Calling 并不意味着没有工作流编排。我的项目仍然使用 LangGraph 管理 Agent Node、工具 Node、条件路由和状态更新。

   - State 负责存数据，Reducer 负责合并数据。
   - Node 负责执行任务，Edge 负责控制执行路径。
   - 条件路由负责动态选择下一步，Send 负责动态分发任务。