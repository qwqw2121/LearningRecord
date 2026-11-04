# Day 1｜Next.js 前端架构与后端接口交互

## 技术面试回答结构

1. **定义**：它是什么？用自己的话解释概念。
2. **目的**：为什么需要它？解决什么问题？
3. **原理**：它内部怎么工作？理解核心机制。
4. **实践**：我在 AI 资讯项目中怎么使用？
5. **取舍**：有什么局限，为什么选择它？

---

## 一、学习内容与记录

### 1. Next.js 和 React 分别是什么？

**定义：**

- React：用于构建用户界面的 JavaScript 库，核心是组件化开发和状态驱动视图。
- Next.js：基于 React 的 Web 开发框架，提供路由、页面组织、服务端渲染、构建和部署等能力。

**目的：**

- React 负责组织页面组件和交互。
- Next.js 在 React 基础上提供完整的应用开发结构，减少自行配置路由和工程工具的工作。

**原理：**

- 页面由多个组件组成，组件通过 JSX 描述界面。
- Props 用于父组件向子组件传递数据。
- State 保存组件内部会变化的数据；状态变化后，React 会重新计算并更新相关界面。
- Next.js 根据项目目录和文件约定组织页面与路由。

**实践：**

在 AI 资讯项目中，Next.js 负责前端页面，例如首页、新闻列表、日报详情和 AI 助手；FastAPI 提供后端数据接口。

**局限与取舍：**

Next.js 并不替代 React，也不自动解决所有前端状态管理问题。项目页面和交互规模适中时，先使用 React 自带的状态能力即可，不必一开始引入复杂状态管理库。

### 2. Next.js App Router 和页面路由

**定义：**

App Router 是 Next.js 的路由系统，基于 `app/` 目录中的文件和文件夹组织页面。

**目的：**

将不同 URL 对应到不同页面，让前端能够通过路径访问首页、新闻详情、日报等内容。

**原理：**

常见文件约定：

| 文件/目录 | 作用 |
|---|---|
| `app/page.tsx` | 对应应用首页 `/` |
| `app/layout.tsx` | 页面共享布局，例如导航栏和整体框架 |
| `app/news/page.tsx` | 对应 `/news` |
| `app/news/[id]/page.tsx` | 动态路由，对应 `/news/具体ID` |
| `app/loading.tsx` | 路由加载时显示的界面 |
| `app/error.tsx` | 路由错误边界界面 |
| `components/` | 通用组件目录，属于项目组织习惯，并非固定路由约定 |

例如：

```text
app/
├── layout.tsx
├── page.tsx
├── news/
│   ├── page.tsx
│   └── [id]/
│       └── page.tsx
└── daily-report/
    └── page.tsx
```

对应 URL：

- `/`：首页
- `/news`：新闻列表
- `/news/123`：ID 为 123 的新闻详情
- `/daily-report`：日报页面

**实践：**

在项目中找到 `app/` 目录，查看 `page.tsx` 和动态路由文件，建立“URL → 页面文件 → 页面组件”的对应关系。

**局限与取舍：**

文件路由降低了路由配置成本，但需要理解动态路由、嵌套路由和布局的匹配规则。不要把 `components/` 中的普通组件误认为路由页面。

### 3. React 组件、Props、State 和事件

**定义：**

- 组件：可复用的 UI 单元。
- Props：组件接收的外部参数。
- State：组件内部需要随交互变化的数据。
- 事件：用户操作触发的逻辑，例如点击按钮、输入文字。

**目的：**

将页面拆分为可维护的模块，并让界面根据数据和用户操作动态变化。

**原理：**

```tsx
"use client";

import { useState } from "react";

export default function Counter() {
  const [count, setCount] = useState(0);

  return (
    <button onClick={() => setCount(count + 1)}>
      点击次数：{count}
    </button>
  );
}
```

- `useState(0)` 创建状态，初始值为 0。
- `count` 是当前状态。
- `setCount()` 更新状态。
- `onClick` 注册点击事件。
- 状态更新后，React 会重新渲染组件。

**实践：**

AI 助手页面可能需要保存：

- 用户输入的问题；
- 聊天消息列表；
- 是否正在生成；
- 当前正在执行的工具名称；
- 工具执行结果和错误信息。

**局限与取舍：**

状态应尽量放在真正需要它的组件或合适的共同父组件中。不要把所有数据都放进全局状态。

### 4. Client Component 和 Server Component

**定义：**

在 App Router 中，组件默认是 Server Component；需要浏览器交互能力的组件通常使用 Client Component。

**目的：**

区分服务端渲染和浏览器交互，减少不必要的客户端 JavaScript。

**原理：**

- Server Component：适合展示内容、在服务端获取数据，不直接使用 `useState`、`useEffect` 等客户端 Hook。
- Client Component：文件顶部使用 `"use client"`，可以使用状态、事件和浏览器 API。
- `"use client"` 是客户端组件边界，不代表整个页面都必须在浏览器中运行。

**实践：**

- 新闻内容展示可以考虑 Server Component。
- AI 助手输入框、发送按钮、流式消息展示需要交互，通常使用 Client Component。

**局限与取舍：**

客户端组件可以实现交互，但会增加发送到浏览器的 JavaScript。应按实际交互需求划分，不要所有组件都加 `"use client"`。

### 5. 前端如何调用 FastAPI 接口？

**定义：**

前端通过 HTTP 请求调用后端 API，后端处理业务逻辑并返回 JSON 或流式响应。

**目的：**

Next.js 负责页面展示和用户交互，FastAPI 负责新闻查询、日报查询、Agent 调用等后端业务。

**原理：**

普通 JSON 请求示例：

```tsx
async function fetchNews() {
  const response = await fetch("http://localhost:8000/api/news");

  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }

  const data = await response.json();
  return data;
}
```

核心步骤：

1. `fetch()` 发起 HTTP 请求。
2. 后端 FastAPI 根据请求方法和 URL 匹配路由。
3. 后端执行对应函数并返回响应。
4. 前端检查 HTTP 状态码。
5. `response.json()` 解析 JSON 响应。
6. 页面将数据保存到状态或作为组件数据展示。

POST 请求示例：

```tsx
const response = await fetch("http://localhost:8000/api/ask", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    question: "今天有哪些重要的 AI 新闻？",
    session_id: "session-001",
  }),
});
```

**实践：**

当前后端 `backend/main.py` 中的接口包括：

| 后端路由 | 用途 |
|---|---|
| `GET /` | 服务基本状态 |
| `GET /api/health` | 健康检查 |
| `POST /api/ask` | 普通问答，等待 Agent 执行完成后返回 |
| `POST /api/chat` | SSE 流式问答 |
| `GET /api/daily-report/today` | 查询今日日报 |
| `GET /api/daily-report/latest` | 查询最新日报 |
| `GET /api/daily-report/range` | 按日期范围查询日报 |
| `GET /api/daily-report/index` | 查询日报索引 |
| `GET /api/daily-report/{report_date}` | 查询指定日期日报 |

注意：新闻、事件、趋势、数据源等路由通过 `include_router()` 注册在其他模块中，具体路径需要继续查看对应的 `backend/api/` 文件。

**局限与取舍：**

前后端分离后，需要维护 API 地址、请求参数和响应结构。接口字段发生变化时，前后端需要同步调整。

### 6. SSE：AI 助手如何接收流式输出？

**定义：**

SSE（Server-Sent Events）是一种服务器向客户端持续发送事件的通信方式。

**目的：**

Agent 生成回答可能需要较长时间。使用流式响应可以逐步展示文本和工具状态，而不是等全部执行完再展示。

**原理：**

项目后端 `/api/chat` 使用 `StreamingResponse`，将异步生成器产生的数据持续发送给前端。消息格式类似：

```text
data: {"type":"token","content":"你好"}

data: {"type":"tool","name":"search_news"}

data: {"type":"tool_end","name":"search_news"}

data: [DONE]
```

前端需要：

1. 发起 POST 请求。
2. 读取响应流（通常通过 `response.body.getReader()`）。
3. 使用 `TextDecoder` 将字节解码为文本。
4. 按 SSE 消息边界解析数据。
5. 根据 `type` 更新聊天消息或工具状态。

**实践：**

项目中的事件类型：

| 事件类型 | 含义 | 前端处理方向 |
|---|---|---|
| `token` | 模型输出文本片段 | 追加到当前回答 |
| `tool` | 工具开始执行 | 展示工具名称或加载状态 |
| `tool_end` | 工具执行结束 | 更新工具执行状态 |
| `error` | 后端发生异常 | 展示错误信息 |
| `[DONE]` | 本次流结束 | 结束加载状态 |

当前后端的 `on_tool_end` 分支只发送工具名称和结束状态，并没有发送工具返回结果本身。因此，若希望前端展示工具的具体输出，需要检查并扩展后端事件数据，同时让前端解析和渲染该数据。

**局限与取舍：**

SSE 适合服务器向客户端单向推送数据；它不是双向通信协议。前端仍通过 HTTP 请求发送问题，后端通过 SSE 返回事件。

### 7. CORS、环境变量和请求失败排查

**定义：**

- CORS：浏览器实施的跨域资源共享机制。
- 环境变量：在应用运行环境中配置的参数，例如 API 地址。

**目的：**

让运行在不同源上的前端和后端能够按规则通信，并避免在代码中写死不同环境的配置。

**原理：**

项目后端配置了 `CORSMiddleware`，允许本地 Next.js 地址，例如：

- `http://localhost:3000`
- `http://127.0.0.1:3000`

线上地址通过 `CORS_ORIGINS` 环境变量配置。

**实践：**

浏览器请求失败时，按顺序检查：

1. Next.js 请求 URL 是否正确。
2. FastAPI 是否启动，接口是否可访问。
3. Network 中请求状态码和响应内容是什么。
4. Console 是否出现 CORS 错误或 JavaScript 异常。
5. 请求方法、请求头、JSON 参数是否符合后端接口要求。
6. 如果是 SSE，检查响应是否为 `text/event-stream`，是否持续收到数据。

**局限与取舍：**

CORS 是浏览器的跨域安全机制，不是后端身份认证。允许跨域不等于接口具备访问权限控制。

---

## 二、实践任务

- [ ] 找到 Next.js 项目的 `app/` 目录，列出主要页面及其 URL。
- [ ] 找到首页、新闻列表、日报、AI 助手对应的页面组件。
- [ ] 找到前端调用 FastAPI 的请求函数，记录请求 URL、方法和参数。
- [ ] 找到 `/api/ask` 和 `/api/chat` 的调用位置，比较普通响应与 SSE 流式响应。
- [ ] 在浏览器 Network 中观察一次新闻查询请求和一次 AI 助手请求。
- [ ] 在聊天页面追踪数据：HTTP 响应 → SSE 解析 → React 状态更新 → 组件渲染。
- [ ] 检查工具事件是否包含工具执行结果，以及前端是否接收并展示。
- [ ] 画一张 Next.js → FastAPI → LangGraph Agent → MCP Tool → SSE/JSON → Next.js 的交互图。
- [ ] 不看笔记，尝试讲 3 分钟前后端交互流程。

---

## 三、学习复盘

**今天还没搞懂的内容：**

- 
- 
- 

**需要面试前回顾的内容：**

- React 组件、Props、State 的区别。
- Next.js App Router 的文件路由规则。
- Server Component 和 Client Component 的区别。
- `fetch` 如何调用 FastAPI，如何处理 JSON 响应。
- SSE 与普通 JSON 响应的区别。
- `useState` 如何驱动页面更新。
- 如何使用 Network 和 Console 定位前后端问题。
- 工具调用结果从后端事件到前端页面的完整链路。

---

## 四、面试表达示例

**问：你的项目中 Next.js 和 FastAPI 是如何协作的？**

答：Next.js 负责前端页面和交互，FastAPI 提供后端 API。对于新闻和日报等数据，前端通过 HTTP 请求获取 JSON；对于 AI 助手，前端向 FastAPI 发送问题，后端调用 LangGraph Agent，使用 SSE 将模型文本和工具状态逐步推送给前端。前端解析事件后更新 React 状态，再由组件完成展示。

**问：AI 助手为什么使用 SSE？**

答：Agent 可能需要多次模型调用和工具执行，整体耗时较长。普通请求通常需要等待后端完成后再返回，而 SSE 可以让后端逐步推送 token 和工具状态，前端能够实时展示执行过程，改善交互体验。

**问：如果工具执行了，但前端没有显示工具结果，怎么排查？**

答：沿数据链路逐层排查。先确认 MCP 工具是否返回结果，再检查 LangGraph 是否产生工具结束事件，接着检查 FastAPI 是否把工具结果放进 SSE 消息；然后通过浏览器 Network 确认前端是否收到数据，最后检查 SSE 解析、React 状态更新和组件渲染。这样可以判断问题发生在哪一层。
