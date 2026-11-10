
## LangGraph 路由
一句话： 看 agent 刚说了什么。没要调工具就结束，要调就按工具分组，把任务并行分给对应的工具节点。
 LangGraph 的条件路由函数，负责根据 Agent 返回的 Tool Call，决定下一步执行哪个工具节点。
```Python
def route_after_agent(state: MessagesState):
    last = state["messages"][-1]                      
    # ① 最后一条消息 = agent 刚产生的 AIMessage
    #HumanMessage：帮我查一下今天的 AI 新闻
    #AIMessage：我需要调用 search_news 工具    此时 last 就是 AIMessage
    tool_calls = getattr(last, "tool_calls", None)    # ② 取工具调用请求；用 getattr 是怕对象没有这个属性   Tool Call 只是模型生成的工具调用请求，还没有真正执行工具。
    #例如模型返回： tool_calls = [
    # {
    #     "name": "search_news",
    #     "id": "call_001",
    #     "args": {"query": "AI"}
    # }
]
    if not tool_calls:                                # ③ 空或 None：模型直接给了答案
        return END                                    #    流程结束
    groups_present = {TOOL_GROUP_MAP.get(c["name"], GROUP_SEARCH) for c in tool_calls}
                                        # ④ 这些调用分属哪几个组（集合会去重）
       #为什么使用集合？  因为这里关心的是本次需要执行哪些工具组，而不是有多少个工具调用。
       #Python 字典 get() 方法的第二个参数：默认值   dict.get(key, default)
    # - 如果字典中存在这个 key，就返回对应的 value。
    # - 如果字典中不存在这个 key，就返回 default。
    #默认使用 GROUP_SEARCH？因为你的代码设计了一条规则：如果工具没有配置分组，就默认归入 search 工具组。
    node_name = {GROUP_SEARCH: "tools_search", GROUP_REPORT: "tools_report"}
    #这是一个字典，GROUP_SEARCH 和 GROUP_REPORT 是键（key），"tools_search" 和 "tools_report" 是值（value）
    return [Send(node_name[g], state) for g in groups_present]
    #node_name[g] 取的就是对应的值,Send("tools_search", state) 就是把这个字符串节点名作为目标节点传给 Send。
    #tools_search\tools_report为图中节点
                                                      # ⑤ 每个组发一个 Send，让对应节点去执行
```
**知识点：**

| 点                                       | 说明                                                         |
| ---------------------------------------- | ------------------------------------------------------------ |
| 路由函数的作用                           | 只读 State，返回「下一步去哪」，自己不执行任何业务           |
| 返回值的三种形式                         | 节点名、`END`、`Send` 列表。这里用了后两种                   |
| `TOOL_GROUP_MAP.get(name, GROUP_SEARCH)` | 查不到的工具默认归入搜索组                                   |
| **Send(节点名, 输入)**                     | 向指定节点投递一次任务。多个 `Send` 在**同一个 superstep 并行执行** |
| 为什么用集合                             | 同一组里有 3 个调用，也只需要发 1 个 `Send`，组内的并发由 ToolNode 处理 |
例子： 假设 LLM 一次输出了两个调用：

```text
tool_calls = [ search_news(keyword="强化学习") id=c1,
               get_daily_report(date="2026-11-09") id=c2 ]
groups_present = {"search", "report"}
返回 [Send("tools_search", state), Send("tools_report", state)]   → 两个节点并行
```
如果只调用了 search_news，就只会有一个 Send，tools_report 不会运行。
Send 是 LangGraph 提供的**动态任务分发机制**，可以在条件路由中指定目标 Node，并传入该 Node 要接收的输入数据。它有两个核心参数：Send(目标Node名称, 输入数据)

**你在 LangGraph 中是如何实现工具路由的？**
我的项目使用条件路由函数 route_after_agent 实现工具分发。
首先，从 State 中获取 Agent 最新返回的 AIMessage，检查其中是否包含 Tool Call。如果没有，就返回 END，结束工作流。
如果存在 Tool Call，就根据工具名称映射到对应的工具组，例如 search 和 report。然后使用 LangGraph 的 Send 动态分发机制，将任务发送到对应的工具节点。
工具节点执行完成后，将 ToolMessage 返回并更新 State，再进入 Agent 节点，由模型整合工具结果并生成最终回答。

 - route_after_agent()：决定调用哪个工具组。
 - _run_tool_group()：接收分配的任务，筛选并执行具体工具。

##  ToolNode 执行
一句话： 从 agent 的调用里挑出属于本组的，交给 ToolNode 执行，并加超时保护，最后一定为每个调用返回一条 ToolMessage。
这段代码实现了 LangGraph 中的工具执行节点：根据 Agent 生成的 Tool Call 筛选对应工具，交给 ToolNode 执行，通过异步超时控制保障执行稳定性，最后将工具结果或超时信息封装为 ToolMessage 返回给 Agent。
```Python
async def _run_tool_group(state, group_tools, group_name):
    last = state["messages"][-1]
    calls = [c for c in (getattr(last, "tool_calls", None) or [])
             if TOOL_GROUP_MAP.get(c["name"], GROUP_SEARCH) == group_name]
    # ① 筛选：只保留属于本组的调用
    if not calls:
        return {"messages": []}                  # ② 本组没有任务，返回空更新（什么都不改）

    node = ToolNode(group_tools)                 # ③ ToolNode 只持有本组的工具
    trimmed = AIMessage(content="", tool_calls=calls)
    # ④ 重新包装一条只含本组调用的 AIMessage，作为 ToolNode 的输入
    timeout_seconds = GROUP_CONFIG[group_name]["timeout_seconds"]

    try:
        result = await asyncio.wait_for(
            node.ainvoke({"messages": [trimmed]}), timeout=timeout_seconds
        )                                        # ⑤ 执行并限时
        return result                            #    返回 {"messages": [ToolMessage, ...]}
    except asyncio.TimeoutError:
        return {"messages": [                    # ⑥ 超时：为每个调用造一条 ToolMessage
            ToolMessage(content="…超时…", tool_call_id=c["id"], name=c["name"])
            for c in calls
        ]}
```
代码作用：从Agent 返回的 Tool Call 中筛选出属于当前工具组的调用，交给 ToolNode 执行，并通过超时控制避免工具执行时间过长。

可以概括为：筛选工具 → 构造 Tool Call → 执行工具 → 处理结果或超时 → 返回 ToolMessage。
ToolNode 是 LangGraph 提供的工具执行节点。
它负责：
1. 接收 AIMessage 中的 Tool Call。
2. 根据工具名称找到对应的工具。
3. 提取 Tool Call 中的参数。
4. 执行对应工具函数。
5. 将执行结果封装成 ToolMessage。
注意区分：
Tool Calling	模型决定调用什么工具，生成调用请求
ToolNode	接收并执行工具调用请求
Tool	真正执行具体业务逻辑的函数
例如，search_news 是实际执行新闻检索的工具函数。
ToolNode 负责调用它。


| 概念                             | 在你代码里的位置                                             |
| -------------------------------- | ------------------------------------------------------------ |
| Tool Calling（模型提出调用请求） | `agent_node` 里 LLM 返回的 `AIMessage.tool_calls`            |
| ToolNode（接收并执行请求）       | `_run_tool_group` 里的 `ToolNode(group_tools)`               |
| Tool（真正干活的函数）           | `search_news`（MCP 工具）、`request_daily_report`（本地 `@tool`） |


```Mermaid
flowchart TD
    A[接收 MessagesState] --> B[获取最后一条 AIMessage]
    B --> C[读取 tool_calls]
    C --> D[根据 TOOL_GROUP_MAP 筛选工具]
    D --> E{当前工具组有调用吗?}
    E -->|没有| F[返回空 messages]
    E -->|有| G[创建 ToolNode]
    G --> H[构造只包含当前组调用的 AIMessage]
    H --> I[获取超时时间并开始计时]
    I --> J[ToolNode.ainvoke]
    J --> K{是否超时?}
    K -->|否| L[打印耗时]
    L --> M[返回 ToolNode 执行结果]
    K -->|是| N[捕获 TimeoutError]
    N --> O[为每个 Tool Call 构造 ToolMessage]
    O --> P[返回超时结果]
 ```

 1. Tool Calling 和 ToolNode 有什么区别？

Tool Calling 是模型生成工具调用请求的过程；ToolNode 是 LangGraph 中负责执行这些请求的节点。模型决定调用什么工具，ToolNode 负责真正执行。

2. 为什么要使用 asyncio.wait_for？

因为工具可能涉及网络请求和数据库查询，执行时间不确定。使用 asyncio.wait_for 可以设置最大等待时间，避免工具长时间阻塞整个工作流。

3. 超时后为什么返回 ToolMessage？

因为模型发出的**每个 Tool Call 都需要对应的执行结果**。返回 ToolMessage 可以将超时信息反馈给 Agent，让 **Agent 根据执行结果决定是否重试或向用户解释**。

4. asyncio.wait_for 和 LangGraph RetryPolicy 有什么区别？
- asyncio.wait_for：控制一次异步操作的最大等待时间。
- RetryPolicy：控制 LangGraph 节点执行失败时是否重新执行。
它们解决的问题不同。你的代码捕获超时异常并返回 ToolMessage，因此超时本身不会自动触发 RetryPolicy。

5. 为什么要把工具分组，而不是所有工具放在一个 ToolNode 中？

工具分组可以隔离不同业务类型的执行逻辑，分别配置超时时间、重试策略，也便于后续扩展和维护。