import discord
from discord.ext import commands
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv
from aiohttp import web
import asyncio

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# MVP Types
MVP_TYPES = {
    'EVENT': '🎯',
    'ROW': '⭐',
    'RANKING': '🏆'
}

# Data storage
DATA_FILE = 'data/mvp_data.json'

def load_data():
    """Load MVP data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        'rotation': [],
        'inactive': [],
        'past_members': [],
        'logs': {
            'events': [],
            'row': [],
            'ranking': []
        },
        'stats': {}  # Will store player stats: {discord_id: {events: 0, row: 0, ranking: 0, titles: 0}}
    }

def save_data(data):
    """Save MVP data to JSON file"""
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def format_player_name(player: Dict) -> str:
    """Format player name with Discord mention"""
    game_name = player.get('game_name', 'Unknown')
    discord_id = player.get('discord_id')
    mention = f"<@{discord_id}>" if discord_id else ""
    return f"**{game_name}** {mention}" if mention else f"**{game_name}**"

def format_rotation_list(data: Dict, next_index: int) -> str:
    """Format the rotation list with proper formatting"""
    rotation = data['rotation']
    if not rotation:
        return "No players in rotation."
    
    lines = []
    has_owed_players = any(p.get('owed', 0) > 0 for p in rotation)
    
    # Find the transition point: first player with owed, or last player without owed
    transition_index = None
    for i, player in enumerate(rotation):
        if player.get('owed', 0) > 0:
            transition_index = i
            break
    
    for i, player in enumerate(rotation):
        game_name = player.get('game_name', 'Unknown')
        discord_id = player.get('discord_id')
        mention = f"<@{discord_id}>" if discord_id else ""
        owed = player.get('owed', 0)
        last_mvp = player.get('last_mvp_type', '')
        mvp_symbol = MVP_TYPES.get(last_mvp, '') if last_mvp else ''
        
        owed_str = f" (+{owed})" if owed > 0 else ""
        
        # Add line break before first player with owed (if there are any)
        # This shows the division between players who got MVP and those who are owed
        if i == transition_index and transition_index is not None and transition_index > 0:
            lines.append("")  # Line break
        
        # Check if last MVP had title
        last_had_title = player.get('last_had_title', False)
        title_emoji = "👑" if last_had_title else ""
        
        if i == next_index:
            # Next player - bigger and bolded
            lines.append(f"**>>> {game_name}** {mention}{owed_str} {mvp_symbol}{title_emoji} <NEXT")
        else:
            # Regular player
            lines.append(f"{game_name} {mention}{owed_str} {mvp_symbol}{title_emoji}")
    
    return "\n".join(lines)

def format_inactive_list(data: Dict) -> str:
    """Format the inactive list"""
    inactive = data.get('inactive', [])
    if not inactive:
        return "No inactive players."
    
    lines = []
    for player in inactive:
        game_name = player.get('game_name', 'Unknown')
        discord_id = player.get('discord_id')
        mention = f"<@{discord_id}>" if discord_id else ""
        lines.append(f"{game_name} {mention}")
    
    return "\n".join(lines)

def format_logs(data: Dict) -> str:
    """Format the MVP logs in three columns"""
    logs = data.get('logs', {})
    events = logs.get('events', [])
    row = logs.get('row', [])
    ranking = logs.get('ranking', [])
    
    # Combine all dates and sort
    all_dates = set()
    for entry in events + row + ranking:
        all_dates.add(entry['date'])
    all_dates = sorted(all_dates)
    
    if not all_dates:
        return "No MVP logs yet."
    
    # Group by month
    lines = []
    current_month = None
    
    for date_str in all_dates:
        date_obj = datetime.strptime(date_str, '%m/%d')
        month = date_obj.strftime('%B')
        
        if month != current_month:
            if current_month is not None:
                lines.append("")
            lines.append(f"**{month}**")
            current_month = month
        
        # Find entries for this date
        event_entry = next((e for e in events if e['date'] == date_str), None)
        row_entry = next((e for e in row if e['date'] == date_str), None)
        ranking_entry = next((e for e in ranking if e['date'] == date_str), None)
        
        # Format line with title indicator
        event_str = ""
        if event_entry:
            title_indicator = " 👑" if event_entry.get('had_title', False) else ""
            event_str = f"{date_str} {event_entry['name']}{title_indicator}"
        
        row_str = ""
        if row_entry:
            title_indicator = " 👑" if row_entry.get('had_title', False) else ""
            row_str = f"{date_str} {row_entry['name']}{title_indicator}"
        
        ranking_str = ""
        if ranking_entry:
            title_indicator = " 👑" if ranking_entry.get('had_title', False) else ""
            ranking_str = f"{date_str} {ranking_entry['name']}{title_indicator}"
        
        # Pad columns
        event_padded = event_str.ljust(25) if event_str else "".ljust(25)
        row_padded = row_str.ljust(25) if row_str else "".ljust(25)
        ranking_padded = ranking_str if ranking_str else ""
        
        lines.append(f"{event_padded}{row_padded}{ranking_padded}")
    
    header = "EVENTS".ljust(25) + "ROW".ljust(25) + "RANKING"
    return f"```\n{header}\n{'-' * 75}\n" + "\n".join(lines) + "\n```"

class PlayerActionView(discord.ui.View):
    """View for player action buttons"""
    def __init__(self, player_id: int, player_name: str):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_name = player_name
    
    @discord.ui.button(label="Complete", emoji="✅", style=discord.ButtonStyle.green, row=0)
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # This will be handled by a modal or follow-up
        await interaction.response.send_message(
            f"Select MVP type for {self.player_name}:",
            view=MVPTypeView(self.player_id, self.player_name),
            ephemeral=True
        )
    
    @discord.ui.button(label="Move Up", emoji="⬆️", style=discord.ButtonStyle.primary, row=0)
    async def move_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        rotation = data.get('rotation', [])
        
        player_index = -1
        for i, player in enumerate(rotation):
            if player.get('discord_id') == self.player_id:
                player_index = i
                break
        
        if player_index == -1:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        if player_index == 0:
            await interaction.response.send_message("Already at top!", ephemeral=True)
            return
        
        rotation[player_index], rotation[player_index - 1] = rotation[player_index - 1], rotation[player_index]
        save_data(data)
        
        await interaction.response.send_message(f"Moved {self.player_name} up!", ephemeral=True)
        
        officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
        if officer_channel:
            next_index = get_next_index(data)
            await update_officer_channel(officer_channel, data, next_index)
    
    @discord.ui.button(label="Move Down", emoji="⬇️", style=discord.ButtonStyle.primary, row=0)
    async def move_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        rotation = data.get('rotation', [])
        
        player_index = -1
        for i, player in enumerate(rotation):
            if player.get('discord_id') == self.player_id:
                player_index = i
                break
        
        if player_index == -1:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        if player_index == len(rotation) - 1:
            await interaction.response.send_message("Already at bottom!", ephemeral=True)
            return
        
        rotation[player_index], rotation[player_index + 1] = rotation[player_index + 1], rotation[player_index]
        save_data(data)
        
        await interaction.response.send_message(f"Moved {self.player_name} down!", ephemeral=True)
        
        officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
        if officer_channel:
            next_index = get_next_index(data)
            await update_officer_channel(officer_channel, data, next_index)
    
    @discord.ui.button(label="To Inactive", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def to_inactive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        rotation = data.get('rotation', [])
        
        player_index = -1
        for i, player in enumerate(rotation):
            if player.get('discord_id') == self.player_id:
                player_index = i
                break
        
        if player_index == -1:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        player = rotation.pop(player_index)
        if 'inactive' not in data:
            data['inactive'] = []
        data['inactive'].append(player)
        save_data(data)
        
        await interaction.response.send_message(f"Moved {self.player_name} to inactive!", ephemeral=True)
        
        officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
        if officer_channel:
            next_index = get_next_index(data)
            await update_officer_channel(officer_channel, data, next_index)

class MVPTypeView(discord.ui.View):
    """View for selecting MVP type"""
    def __init__(self, player_id: int, player_name: str):
        super().__init__(timeout=300)
        self.player_id = player_id
        self.player_name = player_name
    
    @discord.ui.button(label="Event", emoji="🎯", style=discord.ButtonStyle.primary, row=0)
    async def event_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Did {self.player_name} get a title (👑)?",
            view=TitleConfirmView(self.player_id, self.player_name, 'EVENT'),
            ephemeral=True
        )
    
    @discord.ui.button(label="RoW", emoji="⭐", style=discord.ButtonStyle.primary, row=0)
    async def row_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Did {self.player_name} get a title (👑)?",
            view=TitleConfirmView(self.player_id, self.player_name, 'ROW'),
            ephemeral=True
        )
    
    @discord.ui.button(label="Ranking", emoji="🏆", style=discord.ButtonStyle.primary, row=0)
    async def ranking_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Did {self.player_name} get a title (👑)?",
            view=TitleConfirmView(self.player_id, self.player_name, 'RANKING'),
            ephemeral=True
        )

class TitleConfirmView(discord.ui.View):
    """View for confirming if MVP had a title"""
    def __init__(self, player_id: int, player_name: str, mvp_type: str):
        super().__init__(timeout=300)
        self.player_id = player_id
        self.player_name = player_name
        self.mvp_type = mvp_type
    
    @discord.ui.button(label="Yes, got title 👑", emoji="👑", style=discord.ButtonStyle.green, row=0)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.award_mvp(interaction, True)
    
    @discord.ui.button(label="No title", style=discord.ButtonStyle.secondary, row=0)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.award_mvp(interaction, False)
    
    async def award_mvp(self, interaction: discord.Interaction, had_title: bool):
        data = load_data()
        
        player_index = -1
        for i, player in enumerate(data['rotation']):
            if player.get('discord_id') == self.player_id:
                player_index = i
                break
        
        if player_index == -1:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        player = award_mvp(data, player_index, self.mvp_type, had_title)
        
        if player:
            member = interaction.guild.get_member(self.player_id)
            title_text = " 👑" if had_title else ""
            # Announce in public channel
            public_channel = bot.get_channel(int(os.getenv('PUBLIC_CHANNEL_ID')))
            if public_channel and member:
                embed = discord.Embed(
                    title=f"🎉 MVP Awarded! {MVP_TYPES[self.mvp_type]}{title_text}",
                    description=f"**{player['game_name']}** ({member.mention}) has been awarded MVP!{title_text}",
                    color=discord.Color.gold()
                )
                await public_channel.send(embed=embed)
            
            await interaction.response.send_message(f"Awarded {self.mvp_type} MVP to {self.player_name}!{title_text}", ephemeral=True)
            
            # Update channels
            officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
            if officer_channel:
                next_index = get_next_index(data)
                await update_officer_channel(officer_channel, data, next_index)
            
            logs_channel_id = os.getenv('LOGS_CHANNEL_ID', os.getenv('OFFICER_CHANNEL_ID'))
            if logs_channel_id:
                logs_channel = bot.get_channel(int(logs_channel_id))
                if logs_channel:
                    await update_logs_channel(logs_channel, data)
                    await update_stats_channel(logs_channel, data)
        else:
            await interaction.response.send_message("Failed to award MVP!", ephemeral=True)

class InactiveActionView(discord.ui.View):
    """View for inactive player actions"""
    def __init__(self, player_id: int, player_name: str):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_name = player_name
    
    @discord.ui.button(label="Back to Rotation", emoji="✅", style=discord.ButtonStyle.green, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        inactive = data.get('inactive', [])
        
        player_index = -1
        for i, player in enumerate(inactive):
            if player.get('discord_id') == self.player_id:
                player_index = i
                break
        
        if player_index == -1:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        player = inactive.pop(player_index)
        if 'rotation' not in data:
            data['rotation'] = []
        data['rotation'].append(player)
        save_data(data)
        
        await interaction.response.send_message(f"Moved {self.player_name} back to rotation!", ephemeral=True)
        
        officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
        if officer_channel:
            next_index = get_next_index(data)
            await update_officer_channel(officer_channel, data, next_index)
    
    @discord.ui.button(label="Remove", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        inactive = data.get('inactive', [])
        
        player_index = -1
        for i, player in enumerate(inactive):
            if player.get('discord_id') == self.player_id:
                player_index = i
                break
        
        if player_index == -1:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        inactive.pop(player_index)
        save_data(data)
        
        await interaction.response.send_message(f"Removed {self.player_name} from guild!", ephemeral=True)
        
        officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
        if officer_channel:
            next_index = get_next_index(data)
            await update_officer_channel(officer_channel, data, next_index)

class PlayerManagementView(discord.ui.View):
    """Main view for managing players via select menus"""
    def __init__(self, data: Dict, next_index: int):
        super().__init__(timeout=None)
        self.data = data
        self.next_index = next_index
        
        # Create select menu for rotation players
        rotation_options = []
        for i, player in enumerate(data.get('rotation', [])):
            game_name = player.get('game_name', 'Unknown')
            discord_id = player.get('discord_id', 0)
            owed = player.get('owed', 0)
            owed_str = f" (+{owed})" if owed > 0 else ""
            next_str = " <NEXT" if i == next_index else ""
            label = f"{game_name}{owed_str}{next_str}"
            if len(label) > 100:
                label = label[:97] + "..."
            rotation_options.append(discord.SelectOption(
                label=label,
                value=f"rot_{discord_id}",
                description=f"Manage {game_name}"
            ))
        
        if rotation_options:
            self.rotation_select = discord.ui.Select(
                placeholder="Select a player from rotation...",
                options=rotation_options[:25],  # Discord limit
                row=0
            )
            self.rotation_select.callback = self.on_rotation_select
            self.add_item(self.rotation_select)
        
        # Create select menu for inactive players
        inactive_options = []
        for player in data.get('inactive', []):
            game_name = player.get('game_name', 'Unknown')
            discord_id = player.get('discord_id', 0)
            label = game_name
            if len(label) > 100:
                label = label[:97] + "..."
            inactive_options.append(discord.SelectOption(
                label=label,
                value=f"inact_{discord_id}",
                description=f"Manage {game_name}"
            ))
        
        if inactive_options:
            self.inactive_select = discord.ui.Select(
                placeholder="Select an inactive player...",
                options=inactive_options[:25],
                row=1
            )
            self.inactive_select.callback = self.on_inactive_select
            self.add_item(self.inactive_select)
    
    async def on_rotation_select(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        player_id = int(selected.split('_')[1])
        
        # Find player name
        player_name = "Unknown"
        for player in self.data.get('rotation', []):
            if player.get('discord_id') == player_id:
                player_name = player.get('game_name', 'Unknown')
                break
        
        await interaction.response.send_message(
            f"Actions for **{player_name}**:",
            view=PlayerActionView(player_id, player_name),
            ephemeral=True
        )
    
    async def on_inactive_select(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        player_id = int(selected.split('_')[1])
        
        # Find player name
        player_name = "Unknown"
        for player in self.data.get('inactive', []):
            if player.get('discord_id') == player_id:
                player_name = player.get('game_name', 'Unknown')
                break
        
        await interaction.response.send_message(
            f"Actions for **{player_name}** (Inactive):",
            view=InactiveActionView(player_id, player_name),
            ephemeral=True
        )

async def update_officer_channel(channel: discord.TextChannel, data: Dict, next_index: int):
    """Update the officer channel with current rotation"""
    rotation_text = format_rotation_list(data, next_index)
    inactive_text = format_inactive_list(data)
    
    embed = discord.Embed(
        title="MVP Rotation",
        description=f"**Rotation:**\n{rotation_text}\n\n**Inactive:**\n{inactive_text}",
        color=discord.Color.blue()
    )
    
    embed.set_footer(text="Use the dropdowns below to manage players")
    
    # Find existing message or create new one
    view = PlayerManagementView(data, next_index)
    async for message in channel.history(limit=50):
        if message.author == bot.user and message.embeds and "MVP Rotation" in str(message.embeds[0].title):
            await message.edit(embed=embed, view=view)
            return message
    
    # Create new message with view
    message = await channel.send(embed=embed, view=view)
    return message

def format_stats(data: Dict) -> str:
    """Format the stats in three columns: Active | Inactive | Past"""
    stats = data.get('stats', {})
    rotation = data.get('rotation', [])
    inactive = data.get('inactive', [])
    past_members = data.get('past_members', [])
    
    # Get all player data with stats
    active_players = []
    for player in rotation:
        discord_id = player.get('discord_id')
        game_name = player.get('game_name', 'Unknown')
        player_stats = stats.get(str(discord_id), {'events': 0, 'row': 0, 'ranking': 0, 'titles': 0})
        active_players.append({
            'name': game_name,
            'stats': player_stats
        })
    
    inactive_players = []
    for player in inactive:
        discord_id = player.get('discord_id')
        game_name = player.get('game_name', 'Unknown')
        player_stats = stats.get(str(discord_id), {'events': 0, 'row': 0, 'ranking': 0, 'titles': 0})
        inactive_players.append({
            'name': game_name,
            'stats': player_stats
        })
    
    past_players = []
    for player in past_members:
        discord_id = player.get('discord_id')
        game_name = player.get('game_name', 'Unknown')
        player_stats = stats.get(str(discord_id), {'events': 0, 'row': 0, 'ranking': 0, 'titles': 0})
        past_players.append({
            'name': game_name,
            'stats': player_stats
        })
    
    # Format in columns
    lines = []
    max_rows = max(len(active_players), len(inactive_players), len(past_players))
    
    # Header
    header = "ACTIVE MEMBERS".ljust(30) + "INACTIVE MEMBERS".ljust(30) + "PAST MEMBERS"
    lines.append(header)
    lines.append("-" * 90)
    
    # Format each row
    for i in range(max_rows):
        active_str = ""
        if i < len(active_players):
            p = active_players[i]
            s = p['stats']
            # Truncate name if too long
            name = p['name'][:15] if len(p['name']) > 15 else p['name']
            active_str = f"{name}: 🎯{s['events']} ⭐{s['row']} 🏆{s['ranking']} 👑{s['titles']}"
        
        inactive_str = ""
        if i < len(inactive_players):
            p = inactive_players[i]
            s = p['stats']
            name = p['name'][:15] if len(p['name']) > 15 else p['name']
            inactive_str = f"{name}: 🎯{s['events']} ⭐{s['row']} 🏆{s['ranking']} 👑{s['titles']}"
        
        past_str = ""
        if i < len(past_players):
            p = past_players[i]
            s = p['stats']
            name = p['name'][:15] if len(p['name']) > 15 else p['name']
            past_str = f"{name}: 🎯{s['events']} ⭐{s['row']} 🏆{s['ranking']} 👑{s['titles']}"
        
        # Pad columns
        active_padded = active_str.ljust(30) if active_str else "".ljust(30)
        inactive_padded = inactive_str.ljust(30) if inactive_str else "".ljust(30)
        past_padded = past_str if past_str else ""
        
        lines.append(f"{active_padded}{inactive_padded}{past_padded}")
    
    if not lines or max_rows == 0:
        return "No stats available yet."
    
    return f"```\n" + "\n".join(lines) + "\n```"

async def update_logs_channel(channel: discord.TextChannel, data: Dict):
    """Update the logs channel with MVP history"""
    logs_text = format_logs(data)
    
    embed = discord.Embed(
        title="MVP History",
        description=logs_text,
        color=discord.Color.gold()
    )
    
    # Find existing message or create new one
    async for message in channel.history(limit=50):
        if message.author == bot.user and message.embeds and "MVP History" in str(message.embeds[0].title):
            await message.edit(embed=embed)
            return message
    
    # Create new message
    message = await channel.send(embed=embed)
    await message.pin()
    return message

async def update_stats_channel(channel: discord.TextChannel, data: Dict):
    """Update the stats channel with player statistics"""
    stats_text = format_stats(data)
    
    embed = discord.Embed(
        title="MVP Statistics",
        description=stats_text,
        color=discord.Color.purple()
    )
    
    embed.set_footer(text="🎯 Events | ⭐ RoW | 🏆 Ranking | 👑 Titles")
    
    # Find existing message or create new one
    async for message in channel.history(limit=50):
        if message.author == bot.user and message.embeds and "MVP Statistics" in str(message.embeds[0].title):
            await message.edit(embed=embed)
            return message
    
    # Create new message
    message = await channel.send(embed=embed)
    await message.pin()
    return message

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in!')
    print(f'Bot ID: {bot.user.id}')
    # Sync commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
        import traceback
        traceback.print_exc()

@bot.tree.command(name="add_player", description="Add a player to the rotation")
async def add_player(interaction: discord.Interaction, game_name: str, member: discord.Member):
    """Add a player to the rotation"""
    data = load_data()
    
    # Check if player already exists
    for player in data['rotation']:
        if player.get('discord_id') == member.id:
            await interaction.response.send_message(f"{member.mention} is already in the rotation!", ephemeral=True)
            return
    
    # Add player
    new_player = {
        'game_name': game_name,
        'discord_id': member.id,
        'owed': 0,
        'last_mvp_type': ''
    }
    data['rotation'].append(new_player)
    save_data(data)
    
    await interaction.response.send_message(f"Added {game_name} ({member.mention}) to the rotation!", ephemeral=True)
    
    # Update officer channel
    officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
    if officer_channel:
        next_index = get_next_index(data)
        await update_officer_channel(officer_channel, data, next_index)

@bot.tree.command(name="change_name", description="Change a player's in-game name")
async def change_name(interaction: discord.Interaction, member: discord.Member, new_name: str):
    """Change a player's in-game name"""
    data = load_data()
    
    # Update in rotation
    for player in data['rotation']:
        if player.get('discord_id') == member.id:
            player['game_name'] = new_name
            save_data(data)
            await interaction.response.send_message(f"Updated {member.mention}'s name to {new_name}!", ephemeral=True)
            
            # Update officer channel
            officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
            if officer_channel:
                next_index = get_next_index(data)
                await update_officer_channel(officer_channel, data, next_index)
            return
    
    # Update in inactive
    for player in data.get('inactive', []):
        if player.get('discord_id') == member.id:
            player['game_name'] = new_name
            save_data(data)
            await interaction.response.send_message(f"Updated {member.mention}'s name to {new_name}!", ephemeral=True)
            return
    
    await interaction.response.send_message(f"{member.mention} not found in rotation or inactive list!", ephemeral=True)

def get_next_index(data: Dict) -> int:
    """Get the index of the next player in rotation"""
    rotation = data.get('rotation', [])
    if not rotation:
        return -1
    
    # Find first player with owed > 0, otherwise first player
    for i, player in enumerate(rotation):
        if player.get('owed', 0) > 0:
            return i
    return 0

def award_mvp(data: Dict, player_index: int, mvp_type: str, had_title: bool = False):
    """Award MVP to a player and update rotation"""
    rotation = data.get('rotation', [])
    if player_index < 0 or player_index >= len(rotation):
        return None
    
    player = rotation[player_index].copy()
    next_index = get_next_index(data)
    discord_id = player.get('discord_id')
    
    # If player was skipped (has owed), reduce owed
    if player.get('owed', 0) > 0:
        player['owed'] -= 1
    
    # Update last MVP type and title status
    player['last_mvp_type'] = mvp_type
    player['last_had_title'] = had_title
    
    # Update stats
    if 'stats' not in data:
        data['stats'] = {}
    if str(discord_id) not in data['stats']:
        data['stats'][str(discord_id)] = {
            'events': 0,
            'row': 0,
            'ranking': 0,
            'titles': 0
        }
    
    stats = data['stats'][str(discord_id)]
    if mvp_type == 'EVENT':
        stats['events'] = stats.get('events', 0) + 1
    elif mvp_type == 'ROW':
        stats['row'] = stats.get('row', 0) + 1
    elif mvp_type == 'RANKING':
        stats['ranking'] = stats.get('ranking', 0) + 1
    
    if had_title:
        stats['titles'] = stats.get('titles', 0) + 1
    
    # Store original indices before modification
    original_next_index = next_index
    
    # Remove player from current position
    rotation.pop(player_index)
    
    # Adjust next_index if it was after the removed player
    if original_next_index > player_index:
        next_index = original_next_index - 1
    elif original_next_index == player_index:
        # Player was the next person
        next_index = original_next_index
    else:
        # next_index was before player_index, no adjustment needed
        next_index = original_next_index
    
    # Determine who gets marked as owed
    if player_index < original_next_index:
        # Player was chosen before the next person
        # Mark everyone AFTER the next person (they were skipped)
        for i in range(next_index + 1, len(rotation)):
            rotation[i]['owed'] = rotation[i].get('owed', 0) + 1
        # Insert player above the next person
        rotation.insert(next_index, player)
    elif player_index > original_next_index:
        # Player was chosen after the next person
        # Mark everyone from next_index to player_index-1 (they were skipped)
        # After pop, these are at next_index to player_index-1
        for i in range(next_index, player_index):
            rotation[i]['owed'] = rotation[i].get('owed', 0) + 1
        # Insert player above the next person
        rotation.insert(next_index, player)
    else:
        # Player was the next person, just update and keep in place
        rotation.insert(next_index, player)
    
    # Add to logs
    date_str = datetime.now().strftime('%m/%d')
    log_entry = {
        'date': date_str,
        'name': player['game_name'],
        'had_title': had_title
    }
    
    if mvp_type == 'EVENT':
        data['logs']['events'].append(log_entry)
    elif mvp_type == 'ROW':
        data['logs']['row'].append(log_entry)
    elif mvp_type == 'RANKING':
        data['logs']['ranking'].append(log_entry)
    
    save_data(data)
    return player

@bot.tree.command(name="award_mvp", description="Award MVP to a player")
async def award_mvp_command(interaction: discord.Interaction, member: discord.Member, mvp_type: str):
    """Award MVP to a player"""
    if mvp_type.upper() not in MVP_TYPES:
        await interaction.response.send_message(f"Invalid MVP type! Use: EVENT, ROW, or RANKING", ephemeral=True)
        return
    
    data = load_data()
    
    # Find player index
    player_index = -1
    for i, player in enumerate(data['rotation']):
        if player.get('discord_id') == member.id:
            player_index = i
            break
    
    if player_index == -1:
        await interaction.response.send_message(f"{member.mention} not found in rotation!", ephemeral=True)
        return
    
    # Use the button interface for title selection
    player_name = member.display_name
    await interaction.response.send_message(
        f"Did {player_name} get a title (👑)?",
        view=TitleConfirmView(member.id, player_name, mvp_type.upper()),
        ephemeral=True
    )

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reaction events in officer channel"""
    if payload.user_id == bot.user.id:
        return
    
    officer_channel_id = int(os.getenv('OFFICER_CHANNEL_ID', 0))
    if payload.channel_id != officer_channel_id:
        return
    
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    
    try:
        message = await channel.fetch_message(payload.message_id)
    except:
        return
    
    if message.author != bot.user:
        return
    
    user = bot.get_user(payload.user_id)
    if not user:
        return
    
    # Check if user has admin/manage server permissions
    member = channel.guild.get_member(payload.user_id)
    if not member or not (member.guild_permissions.administrator or member.guild_permissions.manage_guild):
        return
    
    data = load_data()
    emoji = str(payload.emoji)
    
    # Parse the embed to find which player was reacted to
    if not message.embeds:
        return
    
    embed = message.embeds[0]
    description = embed.description
    
    # Find player by checking mentions in description
    rotation = data.get('rotation', [])
    inactive = data.get('inactive', [])
    
    # Simple parsing - find the line with the reaction
    # This is a simplified version - in production you'd want more robust parsing
    lines = description.split('\n')
    
    # For now, we'll use a command-based approach instead
    # Reactions will be handled via a separate command system
    
    await message.remove_reaction(payload.emoji, user)

@bot.tree.command(name="complete", description="Mark a player as completed (move them up in rotation)")
async def complete(interaction: discord.Interaction, member: discord.Member):
    """Mark a player as completed"""
    data = load_data()
    
    # Find player
    player_index = -1
    for i, player in enumerate(data['rotation']):
        if player.get('discord_id') == member.id:
            player_index = i
            break
    
    if player_index == -1:
        await interaction.response.send_message(f"{member.mention} not found in rotation!", ephemeral=True)
        return
    
    # Award MVP (this handles the rotation logic)
    # We need to know which type - for now, default to EVENT
    # In practice, you'd want to specify the type
    await interaction.response.send_message("Use /award_mvp to award MVP. This will automatically handle rotation.", ephemeral=True)

@bot.tree.command(name="move_up", description="Move a player up one position")
async def move_up(interaction: discord.Interaction, member: discord.Member):
    """Move a player up one position"""
    data = load_data()
    rotation = data.get('rotation', [])
    
    player_index = -1
    for i, player in enumerate(rotation):
        if player.get('discord_id') == member.id:
            player_index = i
            break
    
    if player_index == -1:
        await interaction.response.send_message(f"{member.mention} not found in rotation!", ephemeral=True)
        return
    
    if player_index == 0:
        await interaction.response.send_message(f"{member.mention} is already at the top!", ephemeral=True)
        return
    
    # Swap with player above
    rotation[player_index], rotation[player_index - 1] = rotation[player_index - 1], rotation[player_index]
    save_data(data)
    
    await interaction.response.send_message(f"Moved {member.mention} up one position!", ephemeral=True)
    
    # Update officer channel
    officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
    if officer_channel:
        next_index = get_next_index(data)
        await update_officer_channel(officer_channel, data, next_index)

@bot.tree.command(name="move_down", description="Move a player down one position")
async def move_down(interaction: discord.Interaction, member: discord.Member):
    """Move a player down one position"""
    data = load_data()
    rotation = data.get('rotation', [])
    
    player_index = -1
    for i, player in enumerate(rotation):
        if player.get('discord_id') == member.id:
            player_index = i
            break
    
    if player_index == -1:
        await interaction.response.send_message(f"{member.mention} not found in rotation!", ephemeral=True)
        return
    
    if player_index == len(rotation) - 1:
        await interaction.response.send_message(f"{member.mention} is already at the bottom!", ephemeral=True)
        return
    
    # Swap with player below
    rotation[player_index], rotation[player_index + 1] = rotation[player_index + 1], rotation[player_index]
    save_data(data)
    
    await interaction.response.send_message(f"Moved {member.mention} down one position!", ephemeral=True)
    
    # Update officer channel
    officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
    if officer_channel:
        next_index = get_next_index(data)
        await update_officer_channel(officer_channel, data, next_index)

@bot.tree.command(name="to_inactive", description="Move a player to inactive list")
async def to_inactive(interaction: discord.Interaction, member: discord.Member):
    """Move a player to inactive list"""
    data = load_data()
    rotation = data.get('rotation', [])
    
    player_index = -1
    for i, player in enumerate(rotation):
        if player.get('discord_id') == member.id:
            player_index = i
            break
    
    if player_index == -1:
        await interaction.response.send_message(f"{member.mention} not found in rotation!", ephemeral=True)
        return
    
    # Move to inactive
    player = rotation.pop(player_index)
    if 'inactive' not in data:
        data['inactive'] = []
    data['inactive'].append(player)
    save_data(data)
    
    await interaction.response.send_message(f"Moved {member.mention} to inactive list!", ephemeral=True)
    
    # Update officer channel
    officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
    if officer_channel:
        next_index = get_next_index(data)
        await update_officer_channel(officer_channel, data, next_index)

@bot.tree.command(name="from_inactive", description="Move a player back from inactive list")
async def from_inactive(interaction: discord.Interaction, member: discord.Member):
    """Move a player back from inactive list"""
    data = load_data()
    inactive = data.get('inactive', [])
    
    player_index = -1
    for i, player in enumerate(inactive):
        if player.get('discord_id') == member.id:
            player_index = i
            break
    
    if player_index == -1:
        await interaction.response.send_message(f"{member.mention} not found in inactive list!", ephemeral=True)
        return
    
    # Move back to rotation
    player = inactive.pop(player_index)
    if 'rotation' not in data:
        data['rotation'] = []
    data['rotation'].append(player)
    save_data(data)
    
    await interaction.response.send_message(f"Moved {member.mention} back to rotation!", ephemeral=True)
    
    # Update officer channel
    officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
    if officer_channel:
        next_index = get_next_index(data)
        await update_officer_channel(officer_channel, data, next_index)

@bot.tree.command(name="remove_player", description="Remove a player from the guild entirely")
async def remove_player(interaction: discord.Interaction, member: discord.Member):
    """Remove a player from the guild entirely (moves to past members)"""
    data = load_data()
    
    # Remove from rotation and move to past_members
    rotation = data.get('rotation', [])
    for i, player in enumerate(rotation):
        if player.get('discord_id') == member.id:
            removed_player = rotation.pop(i)
            if 'past_members' not in data:
                data['past_members'] = []
            data['past_members'].append(removed_player)
            save_data(data)
            await interaction.response.send_message(f"Moved {member.mention} to past members!", ephemeral=True)
            
            # Update channels
            officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
            if officer_channel:
                next_index = get_next_index(data)
                await update_officer_channel(officer_channel, data, next_index)
            
            logs_channel_id = os.getenv('LOGS_CHANNEL_ID', os.getenv('OFFICER_CHANNEL_ID'))
            if logs_channel_id:
                logs_channel = bot.get_channel(int(logs_channel_id))
                if logs_channel:
                    await update_stats_channel(logs_channel, data)
            return
    
    # Remove from inactive and move to past_members
    inactive = data.get('inactive', [])
    for i, player in enumerate(inactive):
        if player.get('discord_id') == member.id:
            removed_player = inactive.pop(i)
            if 'past_members' not in data:
                data['past_members'] = []
            data['past_members'].append(removed_player)
            save_data(data)
            await interaction.response.send_message(f"Moved {member.mention} to past members!", ephemeral=True)
            
            # Update channels
            officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
            if officer_channel:
                next_index = get_next_index(data)
                await update_officer_channel(officer_channel, data, next_index)
            
            logs_channel_id = os.getenv('LOGS_CHANNEL_ID', os.getenv('OFFICER_CHANNEL_ID'))
            if logs_channel_id:
                logs_channel = bot.get_channel(int(logs_channel_id))
                if logs_channel:
                    await update_stats_channel(logs_channel, data)
            return
    
    await interaction.response.send_message(f"{member.mention} not found!", ephemeral=True)

@bot.tree.command(name="refresh", description="Refresh the officer channel display and stats")
async def refresh(interaction: discord.Interaction):
    """Refresh the officer channel display and stats"""
    data = load_data()
    next_index = get_next_index(data)
    
    officer_channel = bot.get_channel(int(os.getenv('OFFICER_CHANNEL_ID')))
    if officer_channel:
        await update_officer_channel(officer_channel, data, next_index)
        await interaction.response.send_message("Refreshed officer channel!", ephemeral=True)
    else:
        await interaction.response.send_message("Officer channel not found!", ephemeral=True)
    
    # Also refresh logs and stats
    logs_channel_id = os.getenv('LOGS_CHANNEL_ID', os.getenv('OFFICER_CHANNEL_ID'))
    if logs_channel_id:
        logs_channel = bot.get_channel(int(logs_channel_id))
        if logs_channel:
            await update_logs_channel(logs_channel, data)
            await update_stats_channel(logs_channel, data)

async def health_check(request):
    """Simple health check endpoint for Render"""
    return web.Response(text="Bot is running!")

def start_http_server():
    """Start HTTP server for Render port detection (runs in background thread)"""
    async def setup_server():
        app = web.Application()
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        # Use PORT environment variable (Render sets this automatically)
        port = int(os.getenv('PORT', 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"HTTP server started on port {port}")
    
    # Run in new event loop in background thread
    import threading
    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(setup_server())
        loop.run_forever()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Error: DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with your bot token.")
    else:
        # Start HTTP server in background thread (for Render port detection)
        start_http_server()
        
        # Start Discord bot (blocking call)
        bot.run(token)
