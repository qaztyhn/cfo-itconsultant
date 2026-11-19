"""Exercise the synthetic E5 draft through the real Compose API and local Chrome UI."""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

import httpx
import websockets

API = "http://127.0.0.1:8004/api/v1"
WEB = "http://127.0.0.1:5174/notifications?order_id=1"
DEBUG = "http://127.0.0.1:9224/json"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def open_tabs() -> list[dict]:
    with urlopen(DEBUG, timeout=1) as response:
        return json.load(response)


class DevTools:
    def __init__(self, connection: object) -> None:
        self.connection = connection
        self.sequence = 0

    async def call(self, method: str, params: dict[str, object] | None = None) -> dict:
        self.sequence += 1
        await self.connection.send(
            json.dumps({"id": self.sequence, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(await self.connection.recv())
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError(f"Browser command failed: {method}")
                return message.get("result", {})

    async def evaluate(self, expression: str) -> object:
        response = await self.call(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
        if "exceptionDetails" in response:
            raise RuntimeError("Browser expression failed")
        return response.get("result", {}).get("value")


async def wait_until(browser: DevTools, phrase: str) -> None:
    for _ in range(40):
        if await browser.evaluate(
            f"document.body?.innerText.includes({json.dumps(phrase)})"
        ):
            return
        await asyncio.sleep(0.25)
    state = await browser.evaluate(
        "({path:location.pathname,signIn:document.body.innerText.includes('Sign in'),"
        "draftsUnavailable:document.body.innerText.includes('Drafts unavailable'),"
        "detailUnavailable:document.body.innerText.includes('Draft detail unavailable'),"
        "loading:document.body.innerText.includes('Loading')})"
    )
    raise RuntimeError(f"UI did not show expected text: {phrase}; state={state}")


async def browser_run(token: str, user: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="e5-chrome-") as profile:
        process = subprocess.Popen(  # noqa: ASYNC220 - local headless browser fixture
            [
                str(CHROME),
                "--headless=new",
                "--no-first-run",
                "--disable-gpu",
                "--remote-debugging-port=9224",
                f"--user-data-dir={profile}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            tabs = None
            for _ in range(40):
                try:
                    tabs = await asyncio.to_thread(open_tabs)
                    break
                except OSError:
                    await asyncio.sleep(0.25)
            if not tabs:
                raise RuntimeError("Local Chrome DevTools did not start")
            tab = next(tab for tab in tabs if tab.get("type") == "page")
            async with websockets.connect(
                tab["webSocketDebuggerUrl"], max_size=8_000_000
            ) as connection:
                browser = DevTools(connection)
                await browser.call("Page.navigate", {"url": WEB})
                await wait_until(browser, "Sign in")
                session = {
                    "cfo_token": token,
                    "cfo_user": json.dumps(user),
                    "cfo_email": "user1@cfo.test",
                    "cfo_expires_at": str(int(time.time() * 1000) + 3_600_000),
                }
                await browser.evaluate(
                    "Object.entries("
                    + json.dumps(session)
                    + ").forEach(([key,value]) => localStorage.setItem(key,value))"
                )
                await browser.call("Page.navigate", {"url": WEB})
                await wait_until(browser, "Saved preview window:")
                text = str(await browser.evaluate("document.body.innerText"))
                if (
                    "ZZ-000001" not in text
                    or "d***@cfo.test" not in text
                    or "Europe/Stockholm" not in text
                ):
                    raise RuntimeError(
                        "Draft order, masked recipient, or timezone is missing from the UI"
                    )
                print(
                    "UI preview: order, masked recipient, market timezone, saved ETA visible"
                )
                clicked = await browser.evaluate(
                    "(() => { const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Send');"
                    " if (!button || button.disabled) return false; button.click(); return true; })()"
                )
                if not clicked:
                    raise RuntimeError("Dispatcher Send button was unavailable")
                await wait_until(browser, "Queued for delivery")
                print("UI Send: queued confirmation visible")
        finally:
            process.terminate()
            process.wait(timeout=5)


def main() -> None:
    if (
        os.getenv("APP_ENV") != "test"
        or os.getenv("DEMO_DISPOSABLE") != "1"
        or not CHROME.exists()
    ):
        raise SystemExit(
            "E5 browser smoke requires the disposable demo and local Chrome."
        )
    with httpx.Client(timeout=10) as client:
        login = client.post(
            API + "/auth/login",
            json={
                "email": "user1@cfo.test",
                "password": os.environ["SEED_DEMO_PASSWORD"],
            },
        )
        login.raise_for_status()
        session = login.json()
        token = session["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get(API + "/notifications/1", headers=headers)
        before.raise_for_status()
        detail = before.json()
        assert detail["status"] == "draft" and detail["eta_window"]["version"] == 1
        asyncio.run(browser_run(token, session["user"]))
        after = client.get(API + "/notifications/1", headers=headers)
        after.raise_for_status()
        assert after.json()["status"] == "queued"
        print("API after UI Send: queued; E5 smoke passed")


if __name__ == "__main__":
    main()
