# Day 10｜LangGraph 进阶与 MCP

## 技术面试回答结构

1. 定义：它是什么？用自己的话解释概念
2. 目的：为什么需要它？理解它解决什么问题
3. 原理：它内部怎么工作？理解核心机制
4. 实践：我在项目中怎么使用？
5. 取舍：有什么局限，为什么选择它？

## 一、学习内容与记录

### 1. Checkpointer、Thread ID、Checkpoint

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

### 2. 状态持久化和多轮对话

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

### 3. MCP Client、Server、Tools、Resources、Prompts

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

### 4. MCP 和普通 HTTP API 有什么区别？

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

### 5. Tool Schema 如何定义？

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

### 6. MCP 如何让 Agent 调用外部工具？

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

## 二、实践任务

- [ ] 找到项目的 MCP Server 代码。
- [ ] 跟踪一次 MCP 工具调用。
- [ ] 解释 Agent、MCP Client、MCP Server 之间的关系。
- [ ] 检查项目是否真正使用了 Checkpoint，不要把了解的功能说成已经实现。

## 三、学习复盘

**今天还没搞懂的内容：**

- Checkpointer 如何根据 Thread ID 保存和恢复状态？状态持久化与长期记忆有什么区别？
- MCP 工具调用时，Client 如何发现工具，Server 又如何执行工具？

**需要面试前回顾的内容：**

- Checkpointer、Thread ID、Checkpoint 分别是什么？
- MCP Client、Server、Tools、Resources、Prompts 有什么区别？
- MCP 和普通 HTTP API 有什么区别？
- Tool Schema 有什么作用？为什么服务端还需要进行参数校验？
- Agent 如何通过 MCP 调用外部工具？