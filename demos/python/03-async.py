import asyncio

async def fetch_news():
    print("开始请求")
    await asyncio.sleep(2) #创建一个等待 2 秒的异步操作。等待这个异步操作完成。
    print("请求完成")
    return "新闻数据"

async def main():
    result = await fetch_news()
    print(result)

asyncio.run(main())