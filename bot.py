import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import asyncio

# ─── Load config ───────────────────────────────────────────────────────────────

with open("config.json") as f:
    cfg = json.load(f)

TOKEN             = cfg["TOKEN"]
GUILD_ID          = int(cfg["GUILD_ID"])
ADMIN_ROLE_ID     = int(cfg["ADMIN_ROLE_ID"])
DESIGNER_ROLE_ID  = int(cfg["DESIGNER_ROLE_ID"])
AUTOROLE_ID       = int(cfg["AUTOROLE_ID"])
WELCOME_CHANNEL   = int(cfg["WELCOME_CHANNEL_ID"])
GOODBYE_CHANNEL   = int(cfg["GOODBYE_CHANNEL_ID"])
EMBED_COLOR       = discord.Color(int(cfg["EMBED_COLOR"].lstrip("#"), 16))

# ─── Bot & Intents ─────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ─── Category & Status Data ────────────────────────────────────────────────────

CATEGORIES = [
    ("ERLC Livery",         "🚗"),
    ("Clothing",            "👕"),
    ("Graphics",            "🎨"),
    ("ELS",                 "🚨"),
    ("Custom Bots",         "🤖"),
    ("Website Orders",      "🌐"),
    ("Discord Services",    "🛠️"),
    ("Photography Orders",  "📸"),
]

category_status = {name: "open" for name, _ in CATEGORIES}

# ─── Helpers ───────────────────────────────────────────────────────────────────

def is_admin():
    async def predicate(inter: discord.Interaction):
        return ADMIN_ROLE_ID in [r.id for r in inter.user.roles]
    return app_commands.check(predicate)

def status_emoji_and_label(name):
    st = category_status[name]
    if st == "open":
        return "🟢", "Open"
    if st == "delayed":
        return "🟡", "Express Only"
    return "🔴", "Closed"

# ─── Views & Modals ────────────────────────────────────────────────────────────

class OrderSelect(ui.Select):
    def __init__(self):
        options = []
        for name, emoji in CATEGORIES:
            st = category_status[name]
            if st == "closed":
                continue
            label = f"{emoji} {name}"
            desc  = "Express package only" if st=="delayed" else None
            options.append(discord.SelectOption(label=label, description=desc))
        super().__init__(placeholder="Choose a product...", min_values=1, max_values=1, options=options)

    async def callback(self, inter: discord.Interaction):
        name = self.values[0].split(" ",1)[1]
        st = category_status[name]
        if st == "delayed":
            await inter.response.send_message(
                "This service is currently only available with the express package. There may be additional fees.",
                ephemeral=True
            )
        await inter.response.send_modal(OrderModal(category=name))

class OrderModal(ui.Modal, title="Place Your Order"):
    category = ui.TextInput(label="Category", default="", required=True, style=discord.TextStyle.short)
    order    = ui.TextInput(label="Order",     placeholder="What do you want?", style=discord.TextStyle.paragraph)
    amount   = ui.TextInput(label="Amount",    placeholder="How many?",       style=discord.TextStyle.short)
    budget   = ui.TextInput(label="Budget",    placeholder="Negotiable?",     style=discord.TextStyle.short)
    delay    = ui.TextInput(label="Delay",     placeholder="When do you need it?", style=discord.TextStyle.short)

    def __init__(self, category: str):
        super().__init__()
        self.category.default = category

    async def on_submit(self, inter: discord.Interaction):
        guild = bot.get_guild(GUILD_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            inter.user:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(DESIGNER_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }
        chan = await guild.create_text_channel(
            name=f"order-{inter.user.name}", category=None, overwrites=overwrites
        )
        embed = discord.Embed(
            title="Thank you for ordering at OMX Studios!",
            description=(
                "The order has successfully been placed.
"
                "Please describe how you would like your order and a designer will answer soon."
            ),
            color=EMBED_COLOR
        )
        embed.add_field(name="Order",   value=self.order.value, inline=False)
        embed.add_field(name="Amount",  value=self.amount.value, inline=True)
        embed.add_field(name="Budget",  value=self.budget.value, inline=True)
        embed.add_field(name="Delay",   value=self.delay.value, inline=False)
        view = TicketStatusView()
        await chan.send(f"<@&{DESIGNER_ROLE_ID}> <@{inter.user.id}>", embed=embed, view=view)
        await inter.response.send_message(f"Your ticket has been created: {chan.mention}", ephemeral=True)

class TicketStatusView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label, style in [("Pending", discord.ButtonStyle.primary),
                             ("In Progress", discord.ButtonStyle.secondary),
                             ("Completed", discord.ButtonStyle.success),
                             ("Cancelled", discord.ButtonStyle.danger)]:
            self.add_item(ui.Button(label=label, style=style, custom_id=f"status_{label.lower()}"))

    @ui.button(label="Pending", style=discord.ButtonStyle.primary, custom_id="status_pending")
    async def pending(self, button: ui.Button, inter: discord.Interaction):
        await update_ticket_status(inter, "Pending")
    @ui.button(label="In Progress", style=discord.ButtonStyle.secondary, custom_id="status_in progress")
    async def in_progress(self, button: ui.Button, inter: discord.Interaction):
        await update_ticket_status(inter, "In Progress")
    @ui.button(label="Completed", style=discord.ButtonStyle.success, custom_id="status_completed")
    async def completed(self, button: ui.Button, inter: discord.Interaction):
        await update_ticket_status(inter, "Completed")
    @ui.button(label="Cancelled", style=discord.ButtonStyle.danger, custom_id="status_cancelled")
    async def cancelled(self, button: ui.Button, inter: discord.Interaction):
        await update_ticket_status(inter, "Cancelled")

async def update_ticket_status(inter: discord.Interaction, new_status: str):
    msg = await inter.channel.fetch_message(inter.message.id)
    embed = msg.embeds[0]
    embed.set_field_at(0, name="Order Status", value=new_status, inline=False)
    await msg.edit(embed=embed, view=inter.message.components[0])
    await inter.response.defer()

class OrderView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Order Here", custom_id="start_order"))

    @ui.button(label="Order Here", style=discord.ButtonStyle.primary, custom_id="start_order")
    async def start(self, button: ui.Button, inter: discord.Interaction):
        await inter.response.send_message(view=CategoryView(), ephemeral=True)

class CategoryView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(OrderSelect())

@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID: return
    await member.add_roles(member.guild.get_role(AUTOROLE_ID))
    chan = member.guild.get_channel(WELCOME_CHANNEL)
    await chan.send(f"Welcome to OMX Studios! We hope you enjoy your stay! For questions and information feel free to contact support.
<@{member.id}>")

@bot.event
async def on_member_remove(member):
    if member.guild.id != GUILD_ID: return
    chan = member.guild.get_channel(GOODBYE_CHANNEL)
    await chan.send("We are sorry to see you go. We hope to see you soon!")

@bot.tree.command(name="setup", description="Initial setup", guild=discord.Object(id=GUILD_ID))
@is_admin()
async def setup(inter: discord.Interaction):
    embed = discord.Embed(title="Order Here", color=EMBED_COLOR)
    embed.description = "Please select the product you'd like to purchase from the options below.

"
    embed.description += "🕘 | **Order Status:**
"
    for name, _ in CATEGORIES:
        emoji, label = status_emoji_and_label(name)
        embed.description += f"• {emoji} **{name}**: {label}
"
    embed.description += "
*Tax not included.*

"
    embed.description += "**Guidelines:**
"
    embed.description += "• Do not abandon the ticket.
"
    embed.description += "• Do not order without the sufficient funds.
"
    embed.description += "• Do not request free items.
"
    view = OrderView()
    await inter.response.send_message(embed=embed, view=view)
    await inter.followup.send("Main order panel deployed.", ephemeral=True)

@app_commands.command(name="server_edit", description="Edit server settings", guild=discord.Object(id=GUILD_ID))
@is_admin()
async def server_edit(inter: discord.Interaction, key: str, value: str):
    if key in category_status:
        category_status[key] = value
        await inter.response.send_message(f"Category **{key}** status set to **{value}**.", ephemeral=True)
    else:
        await inter.response.send_message(f"Unknown key: {key}", ephemeral=True)

@app_commands.command(name="add_admin", description="Grant admin access", guild=discord.Object(id=GUILD_ID))
@is_admin()
async def add_admin(inter: discord.Interaction, user: discord.Member):
    role = inter.guild.get_role(ADMIN_ROLE_ID)
    await user.add_roles(role)
    await inter.response.send_message(f"Granted admin role to {user.mention}", ephemeral=True)

@app_commands.command(name="remove_admin", description="Revoke admin access", guild=discord.Object(id=GUILD_ID))
@is_admin()
async def remove_admin(inter: discord.Interaction, user: discord.Member):
    role = inter.guild.get_role(ADMIN_ROLE_ID)
    await user.remove_roles(role)
    await inter.response.send_message(f"Removed admin role from {user.mention}", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
