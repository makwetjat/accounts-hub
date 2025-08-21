import os
import asyncio
import asyncssh
import shlex
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(root_path="/accountshub")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "root_path": app.root_path})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        import json
        data = await websocket.receive_text()
        params = json.loads(data)

        servers_raw = params.get("servers", "")
        ssh_user = params.get("ssh_user")         # SSH username
        ssh_password = params.get("ssh_password") # SSH password
        target_user = params.get("target_user")   # User to manage
        action = params.get("action")             # add, delete, reset, unlock
        new_password = params.get("new_password", "")  # For reset

        servers = [s.strip() for s in servers_raw.splitlines() if s.strip()]
        if not servers:
            await websocket.send_text("ERROR: No servers provided")
            await websocket.close()
            return

        await websocket.send_text(f"Performing '{action}' on {len(servers)} server(s)...")

        for host in servers:
            await websocket.send_text(f"\n--- Processing {host} ---")
            try:
                async with asyncssh.connect(
                    host, username=ssh_user, password=ssh_password, known_hosts=None
                ) as conn:

                    cmd = ""
                    if action == "add":
                        cmd = f"sudo useradd {shlex.quote(target_user)} && echo 'User {target_user} added.'"
                    elif action == "delete":
                        cmd = f"sudo userdel -r {shlex.quote(target_user)} && echo 'User {target_user} deleted.'"
                    elif action == "reset":
                        cmd = f"echo '{shlex.quote(target_user)}:{shlex.quote(new_password)}' | sudo chpasswd && echo 'Password reset for {target_user}.'"
                    elif action == "unlock":
                        cmd = f"sudo passwd -u {shlex.quote(target_user)} && echo 'User {target_user} unlocked.'"
                    else:
                        await websocket.send_text(f"Unknown action: {action}")
                        continue

                    result = await conn.run(cmd, check=True)
                    await websocket.send_text(result.stdout.strip())
            except Exception as e:
                await websocket.send_text(f"Failed on {host}: {str(e)}")

        await websocket.send_text("\nAll done.")
        await websocket.close()

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_text(f"ERROR: {str(e)}")
        await websocket.close()
