from services.keitaro import KeitaroClient


async def get_keitaro():
    client = KeitaroClient()
    try:
        yield client
    finally:
        await client.aclose()