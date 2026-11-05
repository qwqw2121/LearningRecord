# Day 1｜Next.js 前端架构与后端接口交互

## 技术面试回答结构

1. **定义**：它是什么？用自己的话解释概念。
2. **目的**：为什么需要它？解决什么问题？
3. **原理**：它内部怎么工作？理解核心机制。
4. **实践**：我在 AI 资讯项目中怎么使用？
5. **取舍**：有什么局限，为什么选择它？

---

## 一、学习内容与记录

### 1.  Node.js、Next.js 和 React 分别是什么？

**定义：**
- Node.js：让 JavaScript 在浏览器外运行，负责运行 Next.js 的开发服务器和构建工具。
- React：用于**构建用户界面的 JavaScript 库**，核心是**组件化开发和状态驱动视图**。
- Next.js：基于 React 的 Web 开发框架，提供**路由**、**页面组织、服务端渲染、构建和部署**等能力。
  
Node.js 是运行环境，React 是 UI 库，Next.js 是基于 React 的开发框架。

**目的：**

- React 负责组织**页面组件和交互**。
- Next.js 在 React 基础上提供**完整的应用开发结构**，减少自行配置路由和工程工具的工作。

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
App Router 提供了**基于文件系统的路由机制**。
你只需要按照规定创建文件夹和 page.tsx 文件，Next.js 就能**根据文件路径自动建立 URL 与页面的映射**。

Next.js App Router 使用基于文件系统的路由机制。开发者按照约定在 app 目录下创建文件夹，并在对应目录中创建 page.tsx，Next.js 就会自动将文件路径映射为 URL，不需要像传统 React 项目那样手动配置路由。同时支持动态路由、嵌套路由和共享布局。

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

**在项目中找到 `app/` 目录，查看 `page.tsx` 和动态路由文件，建立“URL → 页面文件 → 页面组件”的对应关系。**

**局限与取舍：**

文件路由降低了路由配置成本，但需要理解**动态路由、嵌套路由和布局**的匹配规则。不要把 `components/` 中的普通组件误认为路由页面。

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

在 App Router 中，组件默认是 Server Component；需要**浏览器交互能力的组件通常使用 Client Component**。

**目的：**

区分服务端渲染和浏览器交互，减少不必要的客户端 JavaScript。

**原理：**

- Server Component：适合展示内容、在服务端获取数据，不直接使用 `useState`、`useEffect` 等客户端 Hook。
- Client Component：文件顶部使用 `"use client"`，可以使用状态、事件和浏览器 API。
- `"use client"` 是**客户端组件边界**，不代表整个页面都必须在浏览器中运行。
Hook 是 React 16.8 引入的函数，让你在函数组件里使用 state、生命周期等能力。
useState：状态管理。管理数据，数据变化时让页面更新。
useEffect：副作用处理，处理组件渲染之后需要执行的操作，例如请求数据、监听事件、设置定时器等。

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

前后端分离后，需要维护 API 地址、请求参数和响应结构。**接口字段发生变化时，前后端需要同步调整**。

###  5.5 fetch() 
fetch() 是 JavaScript 提供的一个 **HTTP 请求 API**，用于**前端向后端发送请求**、获取数据。（浏览器提供给 JS 调用的内置接口（Web API））
Web API = 浏览器（或 JS 运行环境）提供给开发者调用的内置函数/对象。
fetch() 是异步操作。
发送 HTTP 请求需要等待服务器响应，如果采用同步方式，可能阻塞后续代码执行。

重点理解这几个问题：

1. `fetch()` 和 Python 的 `requests` 有什么区别？
   两者都是用于发送 HTTP 请求的工具，但运行环境和异步处理方式不同。
   
| 对比      | JavaScript fetch             | Python requests               |
| --------- | ---------------------------- | ----------------------------- |
| 运行环境  | 浏览器、Node.js              | Python 环境                   |
| 异步方式  | 基于 Promise                 | 默认同步阻塞                  |
| 请求方式  | GET、POST、PUT、DELETE 等    | GET、POST、PUT、DELETE 等     |
| JSON 解析 | `response.json()`            | `response.json()`             |
| 错误处理  | HTTP 404、500 不会自动抛异常 | HTTP 错误默认也不会自动抛异常 |

为什么需要区分？
**前端请求后端时通常使用 fetch()**，Python 后端或数据采集脚本中可以使用 **requests**。
另外，浏览器中的 fetch 受到**同源策略和 CORS 限制**，而 Python requests 不受浏览器同源策略限制。

2. 为什么 `fetch()` 返回的是 Promise？
   因为 HTTP 请求需要等待网络和服务器响应，耗时无法提前确定。

JavaScript 使用 Promise 表示一个尚未完成的异步操作，以及它未来可能产生的结果。
Promise 有三种状态：
Pending	等待中
Fulfilled	操作成功
Rejected	操作失败

3. `async` 和 `await` 分别有什么作用？
   async：声明一个异步函数，该函数始终返回 Promise。
   await：等待一个 Promise 完成，并获取其成功结果；如果失败，则向外抛出异常。
```JavaScript
async function getNews() {
    const response = await fetch("/api/news");
    const data = await response.json();

    return data;
}
```
执行过程：
   1. 调用 getNews()，返回 Promise。
   2. 执行 fetch()，发送 HTTP 请求。
   3. 遇到 await，暂停当前异步函数后续代码的执行。
   4. 请求完成后，继续执行。
   5. 解析 JSON 数据。
   6. 返回新闻数据。
 await 不会阻塞整个 JavaScript 主线程，只是暂停当前 async 函数的后续执行。

4. `response.json()` 和 `JSON.stringify()` 有什么区别？

| 方法               | 作用             | 数据转换方向                  |
| ------------------ | ---------------- | ----------------------------- |
| `response.json()`  | 解析 HTTP 响应体 | JSON → JavaScript 对象        |
| `JSON.stringify()` | 序列化对象       | JavaScript 对象 → JSON 字符串 |

5. HTTP 200、400、404、500 分别代表什么？给我答案
HTTP 状态码用于表示服务器处理 HTTP 请求的结果。

| 状态码 | 含义                  | 解释               | 示例                |
| ------ | --------------------- | ------------------ | ------------------- |
| 200    | OK                    | 请求成功           | 成功获取新闻列表    |
| 400    | Bad Request           | 客户端请求参数错误 | 请求参数格式不正确  |
| 404    | Not Found             | 请求资源不存在     | API 路径不存在      |
| 500    | Internal Server Error | 服务器内部错误     | Python 代码执行异常 |

### 6. SSE：AI 助手如何接收流式输出？

**定义：**

SSE（Server-Sent Events）是一种**服务器向客户端持续发送事件的通信方式。**

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

SSE 适合**服务器向客户端单向推送数据**；它不是双向通信协议。前端仍通过 HTTP 请求发送问题，后端通过 SSE 返回事件。

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

CORS 是浏览器的**跨域安全机制**，不是后端身份认证。允许跨域不等于接口具备访问权限控制。

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

useState：
useState 是 React 提供的状态管理 Hook，用于在函数组件中保存状态。调用它返回当前状态和更新状态的函数。当调用更新函数时，React 会触发组件重新渲染，从而更新 UI。

useEffect：
useEffect 是 React 提供的副作用 Hook，用于处理组件渲染之后的副作用，例如 API 请求、事件监听和定时器。它通过依赖数组控制执行时机，并且可以通过返回清理函数释放资源。
- 
![image-20261105223716050](C:\Users\17761\AppData\Roaming\Typora\typora-user-images\image-20261105223716050.png)

**需要面试前回顾的内容：**

- React 组件、Props、State 的区别。
  Component：组件   组件就是可以复用的 UI 单元。
  Props：组件之间传递的数据   Props 是父组件传递给子组件的数据。
  State：组件内部的状态  State 用来保存组件运行过程中可能变化的数据。
Component 是 React 中构建用户界面的基本单元，用于拆分和复用页面。Props 用于父子组件之间传递数据，属于组件的外部输入，子组件不应该直接修改。State 用于管理组件内部会变化的数据，通过 useState 等 Hook 更新状态，状态变化后 React 会触发重新渲染。

- Next.js App Router 的文件路由规则。
  App Router 是 Next.js 提供的路由系统，基于 app 目录中的文件结构生成路由。page.tsx 定义页面，layout.tsx 定义共享布局，loading.tsx 处理加载状态，error.tsx 处理错误，动态路由通过 [id] 这样的文件夹名称实现。

- ⭐ Server Component 和 Client Component 的区别。
  Next.js App Router 默认采用 Server Component，主要在服务端执行，适合数据获取和静态内容展示，可以减少发送到浏览器的客户端 JavaScript。Client Component 通过在文件顶部声明 use client 来启用，适合需要用户交互、状态管理和浏览器 API 的场景，例如 useState、useEffect 和事件处理。实际开发中通常让页面主体尽量使用 Server Component，将需要交互的部分拆成 Client Component。
Next.js App Router 中，组件默认是 Server Component（服务端组件）。
如果需要在浏览器中处理交互，就需要使用 Client Component（客户端组件）。
- Server Component：服务端组件
服务端组件在服务器端渲染。
特点：
- 默认组件类型，不需要特殊声明。
- 可以在服务端直接获取数据。
- 可以访问服务端资源，例如数据库。
- 不适合直接使用 useState、useEffect 等客户端 Hook。
- 不会把组件本身的完整 JavaScript 代码发送到浏览器执行。

Client Component：客户端组件
客户端组件主要负责浏览器中的交互。

- `fetch` 如何调用 FastAPI，如何处理 JSON 响应。
  前端通过 fetch 发送 HTTP 请求调用 FastAPI 接口。GET 请求用于获取数据，POST 请求可以通过 headers 指定 Content-Type 为 application/json，并使用 JSON.stringify 序列化请求参数。后端 FastAPI 接收并处理请求，返回 JSON 响应，前端通过 response.json() 解析数据，再结合 React State 更新页面。同时需要检查 response.ok，并处理网络异常和 HTTP 错误。

   
- SSE 与普通 JSON 响应的区别。
 普通 JSON 响应适合一次性返回完整数据，例如新闻查询和日报读取。SSE 是基于 HTTP 的服务器推送机制，使用 text/event-stream 格式，可以在一个连接中持续向客户端推送事件。它适合 Agent 流式输出、工具调用状态和任务进度展示。相比普通 JSON，SSE 可以降低用户等待完整结果的感知延迟，但需要处理连接关闭、异常和事件解析。

普通 HTTP 请求通常是：请求 → 后端处理 → 一次性返回完整结果。 适合新闻查询、日报读取、普通数据提交。
SSE 是一种服务器向客户端持续推送事件的机制。前端可以实时接收这些事件，逐步展示 Agent 的执行过程。
FastAPI 可以使用 StreamingResponse实现SSE

- `useState` 如何驱动页面更新。
核心：useState 用来管理 React 组件内部的状态。当状态发生变化时，React 会重新执行组件函数，并根据新的状态更新页面 UI。
useState 是 React 提供的 Hook，用于管理函数组件内部的状态。它返回当前状态值和一个状态更新函数。当我调用更新函数时，React 会将新的状态加入更新流程，重新执行组件函数，并根据新的状态生成 UI，最终通过协调机制更新 DOM 中发生变化的部分。

例如在我的 AI 资讯项目中，搜索新闻时，我使用 useState 管理搜索关键词、新闻列表和加载状态。当 FastAPI 返回查询结果后，通过 setNews 更新新闻列表，React 就会自动更新页面，不需要手动操作 DOM。

**记住这条主线：State 保存数据 → Setter 更新状态 → React 重新渲染 → UI 更新。**
- 如何使用 Network 和 Console 定位前后端问题。
  我主要通过浏览器开发者工具定位前端和前后端交互问题。首先使用 Console 查看 JavaScript 运行错误，然后通过 Network 检查 HTTP 请求，包括 URL、请求方法、请求参数、状态码和响应内容。如果请求已经到达后端，则结合 FastAPI 运行日志定位接口执行和业务逻辑问题，进一步检查数据库查询或 Agent 调用。通过这种方式逐层缩小问题范围。

打开浏览器，按 F12，选择 Network。检查项Request URL  Request Method
Status Code  Request Headers  Payload  Response  Timing
Console 查看前端运行错误，主要用于查看 JavaScript 运行日志和错误。

- 工具调用结果从后端事件到前端页面的完整链路。
  在我的 AI 资讯项目中，用户通过 Next.js 前端提交问题，前端通过 fetch 向 FastAPI 发送请求。FastAPI 将请求交给 LangGraph Agent 执行，Agent 根据用户意图选择 MCP 工具，例如关键词检索或语义检索。MCP Server 执行工具并返回结果，Agent 根据工具结果继续推理并生成最终回答。如果使用流式响应，后端可以将工具调用开始、执行结果和最终回答封装为不同事件，通过 SSE 推送给前端。前端解析事件后，通过 React 的 useState 更新组件状态，实现工具调用过程和回答内容的动态展示。

例如用户在页面点击「生成日报」：
1. Next.js 页面触发按钮事件。
2. 前端 services 使用 fetch() 发送 POST 请求。
3. FastAPI 的 api 路由接收请求。
4. schemas 校验请求参数。
5. services 调用日报生成业务逻辑。
6. 后端调用你的 Agent 或日报生成流程。
7. FastAPI 返回 JSON。
8. Next.js 根据响应更新页面状态。
---

## 四、面试表达示例

**你使用 FastAPI 和 Next.js 搭建的前后端分离项目，前后端是如何交互的？**

项目采用前后端分离架构。后端使用 FastAPI 提供 RESTful API 接口，按照 api、schemas、services 分层组织代码，负责请求处理、参数校验和业务逻辑。前端使用 Next.js 框架，基于 React 和 TypeScript 开发页面，通过 app 目录管理页面路由，使用组件状态管理页面数据，并通过 fetch 封装 HTTP 请求与后端通信。前后端主要通过 HTTP 协议传输 JSON 数据。

**问：你的项目中 Next.js 和 FastAPI 是如何协作的？**

答：Next.js 负责前端页面和交互，FastAPI 提供后端 API。对于新闻和日报等数据，前端通过 HTTP 请求获取 JSON；对于 AI 助手，前端向 FastAPI 发送问题，后端调用 LangGraph Agent，使用 SSE 将模型文本和工具状态逐步推送给前端。前端解析事件后更新 React 状态，再由组件完成展示。

**问：AI 助手为什么使用 SSE？**

答：Agent 可能需要多次模型调用和工具执行，整体耗时较长。普通请求通常需要等待后端完成后再返回，而 SSE 可以让后端逐步推送 token 和工具状态，前端能够实时展示执行过程，改善交互体验。

**问：如果工具执行了，但前端没有显示工具结果，怎么排查？**

答：沿数据链路逐层排查。先确认 MCP 工具是否返回结果，再检查 LangGraph 是否产生工具结束事件，接着检查 FastAPI 是否把工具结果放进 SSE 消息；然后通过浏览器 Network 确认前端是否收到数据，最后检查 SSE 解析、React 状态更新和组件渲染。这样可以判断问题发生在哪一层。
