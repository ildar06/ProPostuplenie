# Entry point for Cloudflare Python Worker
import json

async def on_fetch(request, env):
    if request.method == "POST":
        try:
            payload = await request.json()
            # Handle Telegram update payload here
            return Response("OK", status=200)
        except Exception as e:
            return Response(str(e), status=500)
    
    return Response("Telegram Bot Worker is active", status=200)
