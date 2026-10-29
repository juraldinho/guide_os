import asyncio

from aiohttp.test_utils import TestClient, TestServer

from database.queries import register_user
from services.miniapp_api_settings import MiniAppApiSettings
from web_api.app import create_miniapp_api_app
from web_api.auth import dev_session_token


def test_authenticated_tips_and_reports():
    async def scenario():
        settings = MiniAppApiSettings(enabled=True, dev_auth=True)
        async with TestClient(TestServer(create_miniapp_api_app(settings))) as client:
            register_user(101)
            register_user(102)
            headers = lambda uid: {'Authorization': f'Bearer {dev_session_token(uid)}'}
            url = '/app/v1/daily-tips/1999-01-01'
            assert (await client.get(url)).status == 401
            assert (await client.put(url, json={'amount': 10})).status == 401
            for value in (20, 20, 30):
                r = await client.put(url, headers=headers(101), json={'amount': value})
                assert r.status == 200
                assert (await r.json())['data']['amount'] == value
            r = await client.get(url, headers=headers(102))
            assert (await r.json())['data']['amount'] == 0
            r = await client.get('/app/v1/daily-tips?from=0001-01-01&to=9999-12-31', headers=headers(101))
            assert (await r.json())['data']['tips'] == [{'date': '1999-01-01', 'amount': 30}]
            for uid, expected in ((101, 30), (102, 0)):
                r = await client.get('/app/v1/reports/summary?from=0001-01-01&to=9999-12-31&payment=unpaid&company=absent', headers=headers(uid))
                data = (await r.json())['data']
                assert data['income'] == 0
                assert data['tips'] == data['totalEarnings'] == expected
                assert data['workDays'] == data['tourCount'] == data['paidTours'] == data['unpaidTours'] == 0
            for body in ({'amount': True}, {'amount': -1}, {'amount': 1.5}, {'amount': '10'}, {'amount': 1000000001}, {'amount': 5, 'user_id': 102}, [], {}):
                assert (await client.put(url, json=body, headers=headers(101))).status == 400
            assert (await client.put(url, data='{', headers=headers(101))).status == 400
            assert (await client.put('/app/v1/daily-tips/2026-02-30', json={'amount': 5}, headers=headers(101))).status == 400
            for query in ('from=2026-02-30&to=2026-12-31', 'from=2026-12-31&to=2026-01-01', 'from=2026-01-01', 'from=2026-01-01&from=2026-02-01&to=2026-12-31', 'from=2026-01-01&to=2026-12-31&user_id=102'):
                assert (await client.get('/app/v1/daily-tips?' + query, headers=headers(101))).status == 400
            for _ in range(2):
                assert (await client.put(url, json={'amount': 0}, headers=headers(101))).status == 200
            r = await client.get(url, headers=headers(101))
            assert (await r.json())['data']['amount'] == 0
    asyncio.run(scenario())


def test_real_sessions_are_owner_scoped():
    from web_api.auth import create_miniapp_session, revoke_miniapp_session

    async def scenario():
        register_user(101)
        register_user(102)
        tokens = {uid: create_miniapp_session(uid, 3600)[0] for uid in (101, 102)}
        async with TestClient(TestServer(create_miniapp_api_app(MiniAppApiSettings(enabled=True, dev_auth=False)))) as client:
            headers = lambda uid: {'Authorization': f'Bearer {tokens[uid]}'}
            url = '/app/v1/daily-tips/2026-10-22'
            for uid, amount in ((101, 10), (102, 90)):
                assert (await client.put(url, json={'amount': amount}, headers=headers(uid))).status == 200
            assert (await client.put(url, json={'amount': 0}, headers=headers(101))).status == 200
            r = await client.get(url, headers=headers(102))
            assert (await r.json())['data']['amount'] == 90
            r = await client.get('/app/v1/daily-tips?from=2026-01-01&to=2026-12-31', headers=headers(101))
            assert (await r.json())['data']['tips'] == []
            for uid, expected in ((101, 0), (102, 90)):
                for start, end in (('2026-10-01', '2026-10-31'), ('2026-01-01', '2026-12-31'), ('0001-01-01', '9999-12-31')):
                    r = await client.get(f'/app/v1/reports/summary?from={start}&to={end}', headers=headers(uid))
                    assert (await r.json())['data']['tips'] == expected
            assert (await client.get('/app/v1/reports/summary?from=2026-02-30&to=2026-12-31', headers=headers(101))).status == 400
            revoke_miniapp_session(tokens[101])
            assert (await client.get(url, headers=headers(101))).status == 401
            assert (await client.put(url, json={'amount': 2}, headers=headers(101))).status == 401
    asyncio.run(scenario())
