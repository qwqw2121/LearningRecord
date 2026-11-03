# Day 4｜FastAPI 与数据库

## 技术面试回答结构

1. 定义：它是什么？用自己的话解释概念
2. 目的：为什么需要它？理解它解决什么问题
3. 原理：它内部怎么工作？理解核心机制
4. 实践：我在项目中怎么使用？
5. 取舍：有什么局限，为什么选择它？

## 一、学习内容与记录

### 1. HTTP 请求、GET、POST

**定义：**

HTTP 是客户端和服务端之间进行通信的应用层协议。客户端发送 HTTP 请求，服务端处理后返回 HTTP 响应。

一个 HTTP 请求通常包含：
- 请求方法：GET、POST、PUT、DELETE 等。
- URL：请求的资源地址。
- Headers：请求头，包含认证信息、内容类型等。
- Body：请求体，通常用于传递 JSON 等数据。

GET 和 POST 是常见的 HTTP 请求方法：

| 方法 | 主要用途 | 参数通常放在哪里 |
|---|---|---|
| GET | 查询资源 | URL 查询参数 |
| POST | 创建资源或执行操作 | Request Body |

**目的：**

HTTP 定义了客户端与服务端之间的通信规则。通过 GET 可以查询新闻，通过 POST 可以提交日报生成请求。

**原理：**

以 GET 请求为例：

```http
GET /api/news?limit=10 HTTP/1.1
Host: localhost:8000
```

服务端接收请求，根据 URL 和参数执行对应逻辑，然后返回响应：

```json
{
  "total": 10,
  "items": []
}
```

POST 请求可以通过请求体传递数据：

```http
POST /api/reports HTTP/1.1
Content-Type: application/json

{
  "date": "2026-11-03"
}
```

服务端根据请求体执行相应操作。

需要注意：
- GET 应主要用于读取资源，不应该依赖它执行有副作用的操作。
- POST 常用于创建资源或触发任务。
- GET 请求参数通常会出现在 URL 中，不适合传递敏感信息。
- HTTPS 可以对传输过程进行加密，但不代表服务端自动完成了身份认证和授权。

**实践：**

AI 资讯项目中可以使用 GET 查询新闻：

```python
import requests

response = requests.get(
    "http://localhost:8000/api/news",
    params={"limit": 10}
)

data = response.json()
print(data)
```

也可以使用 POST 请求生成日报：

```python
response = requests.post(
    "http://localhost:8000/api/reports",
    json={"date": "2026-11-03"}
)
```

**局限与取舍：**

GET 适合查询，POST 适合提交数据或触发操作。实际接口设计还需要考虑幂等性、参数大小、权限校验和错误处理。

### 2. FastAPI 路由、参数校验、Pydantic

**定义：**

FastAPI 是基于 Python 的 Web API 框架，可以通过定义路由函数处理 HTTP 请求。

Pydantic 是用于数据校验和结构化的 Python 库。FastAPI 使用 Pydantic 模型校验请求体，并生成 API 文档。

**目的：**

FastAPI 主要解决：
- 接收和处理 HTTP 请求。
- 将请求分发到对应的业务函数。
- 校验请求参数。
- 将 Python 数据转换成 JSON 响应。
- 自动生成 OpenAPI 接口文档。

**原理：**

一个简单的 FastAPI 接口：

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class NewsQuery(BaseModel):
    keyword: str
    limit: int = 10

@app.post("/api/news/search")
def search_news(query: NewsQuery):
    return {
        "keyword": query.keyword,
        "limit": query.limit
    }
```

执行过程：

1. 客户端发送 POST 请求。
2. FastAPI 根据 URL 找到对应路由。
3. 读取请求体中的 JSON。
4. Pydantic 根据 `NewsQuery` 校验数据类型和字段。
5. 校验通过后调用 `search_news()`。
6. 将函数返回值转换为 JSON 响应。

如果参数不符合要求，FastAPI 会返回参数校验错误，通常是 HTTP 422。

**实践：**

AI 资讯项目中，FastAPI 可以提供新闻查询、语义检索和日报查询接口。

例如，新闻查询接口可以设计为：

```python
from fastapi import FastAPI, Query

app = FastAPI()

@app.get("/api/news")
def get_news(
    limit: int = Query(default=10, ge=1, le=100),
    keyword: str | None = None
):
    return {
        "limit": limit,
        "keyword": keyword
    }
```

其中：
- `limit` 是查询参数。
- `ge=1` 表示最小值为 1。
- `le=100` 表示最大值为 100。
- `keyword` 是可选参数。

**局限与取舍：**

FastAPI 适合构建 Python API 服务，但它本身不是完整的业务系统。

实际项目还需要处理数据库连接、日志、认证、权限、异常处理和服务部署等问题。

### 3. 依赖注入

**定义：**

依赖注入（Dependency Injection，DI）是一种设计方式：一个函数需要使用某个对象或服务时，不在函数内部直接创建，而是由外部提供。

FastAPI 通过 `Depends()` 实现依赖注入。

**目的：**

主要解决：
- 减少重复创建对象的代码。
- 将业务逻辑与基础设施解耦。
- 统一管理数据库连接、认证等公共逻辑。
- 方便测试和替换依赖。

**原理：**

示例：

```python
from fastapi import FastAPI, Depends

app = FastAPI()

def get_db():
    db = create_database_connection()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/news")
def get_news(db=Depends(get_db)):
    return db.query_news()
```

执行过程：

1. 请求进入 `/api/news`。
2. FastAPI 发现路由函数依赖 `get_db`。
3. 执行 `get_db()` 获取数据库连接。
4. 将连接传给 `get_news()`。
5. 请求结束后，执行生成器依赖中的清理逻辑，关闭连接。

这里的 `yield` 可以让依赖在请求处理前提供资源，在处理结束后执行清理。

**实践：**

项目中可以将数据库访问封装为依赖：

```python
def get_news_repository():
    return NewsRepository()

@app.get("/api/news")
def get_news(repo=Depends(get_news_repository)):
    return repo.get_latest_news()
```

这样路由层不需要关心 Repository 如何创建。

**局限与取舍：**

依赖注入可以降低耦合，但依赖层级过多会增加代码跳转和调试成本。

简单项目不需要过度封装，数据库连接、认证等公共资源适合使用依赖注入。

### 4. SQLite 基础、SQL 查询

**定义：**

SQLite 是一个轻量级关系型数据库，数据可以直接存储在本地文件中，不需要单独运行数据库服务。

SQL 是用于操作关系型数据库的语言。

常见 SQL 操作：

```sql
-- 查询
SELECT * FROM news;

-- 条件查询
SELECT * FROM news
WHERE category = 'LLM';

-- 排序
SELECT * FROM news
ORDER BY published_at DESC;

-- 限制返回数量
SELECT * FROM news
LIMIT 10;

-- 插入
INSERT INTO news (title, category)
VALUES ('新闻标题', 'LLM');

-- 更新
UPDATE news
SET category = 'AI'
WHERE id = 1;

-- 删除
DELETE FROM news
WHERE id = 1;
```

**目的：**

数据库用于持久化保存结构化数据，避免程序结束后数据丢失。

AI 资讯项目需要保存新闻、分类、摘要、日报、处理状态等信息，因此使用 SQLite 管理结构化数据。

**原理：**

关系型数据库通过表、行、列组织数据。

例如新闻表：

| id | title | category | status |
|---|---|---|---|
| 1 | 新闻A | LLM | analyzed |
| 2 | 新闻B | Agent | embedded |

查询时，数据库根据 SQL 条件找到符合要求的记录并返回结果。

SQLite 将数据库保存为文件，程序可以通过 Python 的 `sqlite3` 模块连接：

```python
import sqlite3

conn = sqlite3.connect("storage/news.db")
conn.row_factory = sqlite3.Row

cursor = conn.cursor()

cursor.execute(
    "SELECT id, title FROM news WHERE status = ? LIMIT ?",
    ("analyzed", 10)
)

rows = cursor.fetchall()

for row in rows:
    print(dict(row))

conn.close()
```

其中 `?` 是参数占位符，可以避免通过字符串拼接 SQL 参数造成 SQL 注入风险。

**实践：**

AI 资讯项目使用 SQLite 的 `storage/news.db` 保存结构化新闻数据。

例如：
- 查询新闻列表。
- 根据日期查询新闻。
- 查询新闻分析结果。
- 保存每日新闻报告。
- 记录新闻处理状态。

需要区分：SQLite 保存结构化业务数据，Chroma 保存向量及相关元数据，两者承担不同职责。

**局限与取舍：**

SQLite 的优点：
- 无需单独部署数据库服务。
- 使用简单，适合个人项目和轻量级应用。
- 数据库文件方便备份和迁移。

局限：
- 并发写入能力有限。
- 不适合大量用户同时进行高频写操作的场景。
- 多实例部署时需要额外考虑共享存储和并发问题。

### 5. 数据库索引、事务

**定义：**

索引是数据库为了提高查询效率建立的数据结构。

事务（Transaction）是数据库执行的一组操作，这些操作要么全部成功，要么按照事务规则回滚。

**目的：**

索引：减少查询时需要扫描的数据，提高查询速度。

事务：保证多个数据库操作作为一个整体执行，避免只完成部分操作导致数据不一致。

**原理：**

索引通常使用 B-tree 或 B+tree 等数据结构组织索引键与数据位置。

例如：

```sql
CREATE INDEX idx_news_published_at
ON news(published_at);
```

查询：

```sql
SELECT * FROM news
ORDER BY published_at DESC
LIMIT 10;
```

如果索引适用，数据库可以利用索引减少扫描和排序成本。

事务通常具有 ACID 特性：

- Atomicity：原子性，操作全部成功或全部回滚。
- Consistency：一致性，事务前后满足数据库约束。
- Isolation：隔离性，并发事务之间按照隔离规则执行。
- Durability：持久性，提交后的数据能够持久保存。

Python 示例：

```python
import sqlite3

conn = sqlite3.connect("storage/news.db")

try:
    conn.execute(
        "UPDATE news SET status = ? WHERE id = ?",
        ("analyzed", 1)
    )

    conn.execute(
        "INSERT INTO crawl_logs (source, status) VALUES (?, ?)",
        ("rss_source", "success")
    )

    conn.commit()

except Exception:
    conn.rollback()
    raise

finally:
    conn.close()
```

**实践：**

项目中可以根据实际查询条件，为新闻发布时间、分类、状态等经常用于过滤或排序的字段建立索引。

在一次业务操作需要同时更新多张表时，可以考虑使用事务。

例如，保存事件聚类结果时，需要同时写入 `events` 和 `event_news` 表，应该考虑保证两部分写入的一致性。

**局限与取舍：**

索引不是越多越好：
- 索引会占用额外磁盘空间。
- INSERT、UPDATE、DELETE 时可能需要维护索引。
- 需要根据实际查询语句决定是否建立索引。

事务也会带来锁竞争和额外开销，应合理控制事务范围。

### 6. ORM 与直接 SQL 的区别

**定义：**

ORM（Object Relational Mapping，对象关系映射）是一种将数据库表映射为 Python 对象的技术。

直接 SQL 是开发者自己编写 SQL 语句操作数据库。

例如 ORM 可以将一条新闻记录映射为 Python 对象：

```python
news.title
news.category
```

而直接 SQL 需要编写：

```sql
SELECT title, category
FROM news
WHERE id = 1;
```

**目的：**

ORM 希望减少重复 SQL 编写工作，让开发者使用面向对象的方式操作数据库。

直接 SQL 则提供更明确的查询控制能力。

**原理：**

ORM 通常包含：
- 模型定义：描述表结构。
- 映射关系：将 Python 类和数据库表关联。
- 查询接口：将 Python 表达式转换为 SQL。
- 执行与结果映射：执行 SQL 并将结果转换为对象。

**实践：**

SQLAlchemy 示例：

```python
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

engine = create_engine("sqlite:///storage/news.db")

with Session(engine) as session:
    statement = select(News).where(News.id == 1)
    news = session.execute(statement).scalar_one_or_none()

    if news:
        print(news.title)
```

直接 SQL 示例：

```python
import sqlite3

conn = sqlite3.connect("storage/news.db")
conn.row_factory = sqlite3.Row

row = conn.execute(
    "SELECT * FROM news WHERE id = ?",
    (1,)
).fetchone()

print(dict(row) if row else None)
conn.close()
```

**局限与取舍：**

ORM 优点：
- 减少重复 SQL。
- 适合复杂业务模型。
- 方便维护对象关系。

ORM 局限：
- 需要学习额外的抽象层。
- 复杂查询可能不如直接 SQL 直观。
- 不理解 ORM 生成的 SQL，容易产生性能问题。

直接 SQL 优点：
- 查询逻辑明确。
- 对复杂 SQL 的控制能力更强。
- 适合简单的数据访问和性能敏感场景。

选择方式应根据项目复杂度决定，两者也可以混合使用。

## 二、实践任务

- [ ] 找到项目中 FastAPI 的接口入口。
- [ ] 跟踪一次新闻查询请求，从 API 到数据库。
- [ ] 自己写一个简单的新闻查询接口。
- [ ] 找到项目中数据库连接和 SQL 查询代码。
- [ ] 查看新闻表有哪些索引。

## Day 4｜FastAPI 与数据库

### 三、学习复盘

**今天还没搞懂的内容：**

- 一个 HTTP 请求从进入 FastAPI 到执行路由函数，中间经历了哪些步骤？
  
- FastAPI 如何根据请求路径找到对应的路由？请求参数和请求体分别如何解析？
  
- Pydantic 的类型校验发生在什么时候？校验失败后为什么会返回 422？
  
- `Depends()` 如何解析依赖关系？数据库连接为什么可以通过 `yield` 在请求结束后关闭？
  
- SQLite 的事务在什么情况下需要提交或回滚？如果程序执行到一半发生异常，数据会怎样？
  
- 数据库索引为什么能加快查询？建立索引后，为什么写入操作可能变慢？
  
- SQLite 和 Chroma 分别保存什么数据？如果新闻已经写入 SQLite，但 Embedding 写入 Chroma 失败，应该如何处理？

**需要面试前回顾的内容：**

- GET 和 POST 的区别，以及 HTTP 请求和响应的基本结构。
  
- FastAPI 从接收请求、路由匹配、参数校验到返回响应的执行过程。
  
- Pydantic 的作用，以及路径参数、查询参数和请求体的区别。
  
- 依赖注入的目的，`Depends()` 的基本执行机制。
  
- SQLite 的基本 SQL 操作、索引和事务 ACID 特性。
  
- ORM 与直接 SQL 的区别，以及各自适用场景。
  
- 为什么项目使用 SQLite 保存结构化新闻数据，而不是全部存入 Chroma？
  
- 如果 API 查询数据库失败，应该在哪一层处理异常？如何避免将数据库内部错误直接暴露给用户？
  
- 如果新闻数据和向量数据写入不一致，如何设计重试、状态记录和数据补偿？
