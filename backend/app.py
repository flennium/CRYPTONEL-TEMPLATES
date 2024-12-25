import uuid
import json
import os
import asyncio
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import threading

TEMPLATES_FILE = "templates.json"
SUBMITS_CHANNEL_ID = SUBMITS_CHANNEL_ID
DISCORD_BOT_TOKEN = "DISCORD_BOT_TOKEN"
FRONTEND_DIR = os.path.abspath("frontend")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="-", intents=intents)

class Template(BaseModel):
    name: str
    description: str
    image_url: str
    roles: list[str]
    channels: list[str]

def load_templates():
    if os.path.exists(TEMPLATES_FILE):
        try:
            with open(TEMPLATES_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Error: Invalid JSON in templates file.")
    return {"pending": {}, "approved": []}

def save_templates(data):
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(data, f, indent=4)

template_submission_queue = asyncio.Queue()

class TemplateView(View):
    def __init__(self, template_id: str):
        super().__init__()
        self.template_id = template_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        templates = load_templates()
        template = templates["pending"].pop(self.template_id, None)
        
        for child in self.children:
            child.disabled = True
        
        if template:
            templates["approved"].append(template)
            save_templates(templates)

            await interaction.response.edit_message(
                content="**Template approved.**", view=self
            )
            self.stop()
        else:
            await interaction.response.edit_message(
                content="**Template no longer exists.**", view=self
            )
            self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(self.template_id)
        templates = load_templates()
        
        for child in self.children:
            child.disabled = True
        
        if self.template_id in templates["pending"]:
            templates["pending"].pop(self.template_id)
            save_templates(templates)

            await interaction.response.edit_message(
                content="**Template declined.**", view=self
            )
            self.stop()
        else:
            await interaction.response.edit_message(
                content="**Template no longer exists.**", view=self
            )
            self.stop()

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    process_queue.start()

async def process_template_submission(template_data, template_id):
    try:
        channel = bot.get_channel(SUBMITS_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="New Template Submission",
                description=f"**TemplateID:** {template_id}\n **Name:** {template_data['name']}\n**Description:** {template_data['description']}\n"
                            f"**Roles:** {', '.join(template_data['roles'])}\n**Channels:** {', '.join(template_data['channels'])}",
                color=0x00FF00
            )
            view = TemplateView(template_id)
            await channel.send(embed=embed, view=view)
        else:
            print(f"Failed to find channel with ID {SUBMITS_CHANNEL_ID}")
    except Exception as e:
        print(f"Error sending template: {e}")

@tasks.loop(seconds=5)
async def process_queue():
    if not template_submission_queue.empty():
        template_data, template_id = await template_submission_queue.get()
        await process_template_submission(template_data, template_id)

@app.get("/templates", response_class=HTMLResponse)
async def get_templates_page():
    try:
        templates = load_templates()["approved"]
        file_path = os.path.join(FRONTEND_DIR, "templates.html")
        if not os.path.exists(file_path):
            return HTMLResponse(content="<h1>Template file not found</h1>", status_code=404)
        with open(file_path, "r") as file:
            html_content = file.read()
        template_cards = "".join(
            f"<div class='template-card'>"
            f"<img src='{t['image_url']}' alt='{t['name']}'>"
            f"<h3>{t['name']}</h3>"
            f"<p>{t['description']}</p>"
            f"<p><strong>Roles:</strong> {', '.join(t['roles'])}</p>"
            f"<p><strong>Channels:</strong> {', '.join(t['channels'])}</p>"
            f"</div>" for t in templates
        )
        return HTMLResponse(html_content.replace("<!-- here is templates uwu -->", template_cards))
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)


@app.get("/submit", response_class=HTMLResponse)
async def get_submit():
    file_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        return HTMLResponse(content="<h1>404 - Not Found</h1>", status_code=404)

@app.post("/submit-template/")
async def submit_template(template: Template):
    template_data = template.model_dump()
    template_id = str(uuid.uuid4())
    templates = load_templates()
    templates["pending"][template_id] = template_data
    save_templates(templates)
    await template_submission_queue.put((template_data, template_id))
    return {"status": "success", "message": "Template submitted successfully and is awaiting approval."}

def start_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=6969)

async def main():
    fastapi_thread = threading.Thread(target=start_fastapi)
    fastapi_thread.start()
    await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
