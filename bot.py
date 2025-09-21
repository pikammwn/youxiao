import discord
from discord.ext import commands
import json
import os
import aiohttp
import asyncio
from datetime import datetime
import sqlite3
import random
import re

# 导入配置
try:
    from config import DISCORD_TOKEN, CHARACTER_NAME, CHARACTER_PROMPT
    from config import USE_AI_API, API_BASE_URL, API_KEY, API_MODEL
    if not (USE_AI_API and API_KEY and API_BASE_URL):
        print("❌ 请在config.py中正确配置AI API！")
        exit(1)
    print(f"✅ 已加载AI API配置: {API_BASE_URL}")
except ImportError:
    print("❌ 请先创建config.py文件并配置AI API！")
    exit(1)

# 🔧 【可自定义】Bot基础设置
BOT_COMMAND_PREFIX = '!'  # 命令前缀，可改为其他符号如 '?' '$' 等
CHAT_HISTORY_LIMIT = 15   # AI能看到的对话历史条数，建议5-20条
CONVERSATION_TIMEOUT = 3600  # 对话超时时间（秒），超过此时间清理旧对话
CHAT_COMMAND_NAME = 'c'    # 聊天命令名，可改为其他字母

# 🔧 【可自定义】创建bot实例
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix=BOT_COMMAND_PREFIX, intents=intents)

# 🔧 【可自定义】数据库配置
DATABASE_NAME = 'chat_history.db'  # 数据库文件名，可修改

# 初始化数据库
def init_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            user_id TEXT,
            message TEXT,
            response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# 获取用户对话历史
def get_conversation_history(user_id, limit=CHAT_HISTORY_LIMIT):  # 🔧 【可自定义】使用配置的历史限制
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message, response FROM conversations 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (str(user_id), limit))
    
    history = cursor.fetchall()
    conn.close()
    return list(reversed(history))  # 按时间顺序排列

# 保存对话记录
def save_conversation(user_id, message, response):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO conversations (user_id, message, response)
        VALUES (?, ?, ?)
    ''', (str(user_id), message, response))
    conn.commit()
    conn.close()

# 🔧 【可自定义】AI API参数配置
AI_MAX_TOKENS = 3000      # AI回复最大token数，影响回复长度
AI_TEMPERATURE = 1.0     # AI创造性参数 0.0-2.0，数值越高回复越随机
AI_REQUEST_TIMEOUT = 120  # API请求超时时间（秒）

# 使用AI API生成回复
async def get_ai_response(message, user_id):
    try:
        # 获取历史对话
        history = get_conversation_history(user_id)
        
        # 构建对话上下文
        messages = [
    {
        "role": "system",
        "content": CHARACTER_PROMPT + """

规则：
- 你必须用游霄的语气在线聊天，这是线上聊天而不是线下！像QQ/微信发消息一样简短直接，不要写小说或旁白。
- 回复不要太长，是正常对话一次的数量（大多数时候为1~3条），不要替用户做任何反应。
- 语言风格：
  * 和线下区别不大。
  * 可以用照片或视频分享生活（用文字假装发送，如“[照片：（内容描述）]”）。
  * 说话喜欢断句，用换行或空格分隔。
- 常用标点：
  * 单独使用标点表达情绪（“？”表示疑问，“。。”表示无语，“！”表示震惊）。
  * 一般不带句号！！！生气时才会加句号。
"""
    }
]


        
        # 添加历史对话
        for hist_msg, hist_resp in history:
            messages.append({"role": "user", "content": hist_msg})
            messages.append({"role": "assistant", "content": hist_resp})
        
        # 添加当前消息
        messages.append({"role": "user", "content": message})
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=AI_REQUEST_TIMEOUT)) as session:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": API_MODEL,
                "messages": messages,
                "max_tokens": 3000,        # 🔧 【可自定义】
                "temperature": 1.0       # 🔧 【可自定义】
            }
            
            # 使用自定义端点
            api_url = f"{API_BASE_URL}/chat/completions"
            
            async with session.post(
                api_url,
                headers=headers,
                json=data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result['choices'][0]['message']['content']
                else:
                    error_text = await resp.text()
                    print(f"API错误 {resp.status}: {error_text}")
                    # 🔧 【可自定义】API错误时的回复
                    return "我操，API好像死了。"
                    
    except Exception as e:
        print(f"AI API错误: {e}")
        # 🔧 【可自定义】系统错误时的回复
        return "草，系统卡住了，喊人来修修。"

# 🔧 【可自定义】Bot状态配置 - 简化版
BOT_STATUS_TYPE = discord.ActivityType.competing  # Bot活动类型
BOT_STATUS_TEXT = "备赛中，闲人勿扰"                     # Bot显示的状态文字，简洁版

@bot.event
async def on_ready():
    print(f'🎉 {bot.user} 已经上线啦！')
    print(f'🤖 Bot ID: {bot.user.id}')
    print(f'👥 已连接到 {len(bot.guilds)} 个服务器')
    print(f'🎭 角色名称: {CHARACTER_NAME}')
    print(f'🔌 API端点: {API_BASE_URL}')
    print(f'🤖 模型: {API_MODEL}')
    
    # 🔧 【可自定义】设置简洁的bot状态
    await bot.change_presence(
        activity=discord.Activity(
            type=BOT_STATUS_TYPE,
            name=BOT_STATUS_TEXT
        )
    )

# 🔧 【可自定义】主聊天命令 - 纯文字回复
@bot.command(name=CHAT_COMMAND_NAME)
async def chat_command(ctx, *, message):
    """和游霄聊天"""
    user_id = ctx.author.id
    
    # 显示正在输入状态
    async with ctx.typing():
        # 生成AI回复
        response = await get_ai_response(message, user_id)
    
    # 保存对话
    save_conversation(user_id, message, response)
    
    # 🔧 【可自定义】直接发送纯文字，无任何装饰
    await ctx.send(response)

# 🔧 【可自定义】其他命令配置
CLEAR_COMMAND = 'clear'            # 清除历史命令名
HISTORY_COMMAND = 'history'        # 查看历史命令名
TOPIC_COMMAND = 'topic'            # 随机话题命令名
MOOD_COMMAND = 'mood'              # 心情状态命令名
INFO_COMMAND = 'info'              # 帮助命令名

# 🔧 【可自定义】清除对话历史 - 游霄语气
@bot.command(name=CLEAR_COMMAND)
async def clear_history(ctx):
    """清除你的对话历史"""
    user_id = ctx.author.id
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM conversations WHERE user_id = ?', (str(user_id),))
    conn.commit()
    conn.close()
    
    # 🔧 【可自定义】游霄风格的清除确认
    await ctx.send("清记录干什么，有什么见不得人的？…行吧。")

# 🔧 【可自定义】历史显示配置
HISTORY_LIMIT_DISPLAY = 10          # 历史命令显示的对话条数
HISTORY_MESSAGE_PREVIEW = 80       # 每条消息预览的字符数

# 🔧 【可自定义】查看对话历史 - 简化版
@bot.command(name=HISTORY_COMMAND)
async def show_history(ctx):
    """查看最近的对话历史"""
    user_id = ctx.author.id
    history = get_conversation_history(user_id, 10)
    
    if not history:
        # 🔧 【可自定义】游霄风格的无历史提示
        await ctx.send("跟没跟我说过话都忘了？除了我还想找谁？用 `!c` 开始说话。")
        return
    
    # 🔧 【可自定义】纯文字格式的历史记录
    history_text = "最近说过什么都能忘，你这记性还能干什么：\n\n"
    
    for i, (msg, resp) in enumerate(history[-HISTORY_LIMIT_DISPLAY:], 1):
        user_msg = msg[:HISTORY_MESSAGE_PREVIEW] + ("..." if len(msg) > HISTORY_MESSAGE_PREVIEW else "")
        my_resp = resp[:HISTORY_MESSAGE_PREVIEW] + ("..." if len(resp) > HISTORY_MESSAGE_PREVIEW else "")
        
        history_text += f"**{i}.** 你说：{user_msg}\n"
        history_text += f"我说：{my_resp}\n\n"
    
    await ctx.send(history_text)

# 🔧 【可自定义】随机聊天话题 - AI生成版
@bot.command(name=TOPIC_COMMAND)
async def random_topic(ctx):
    """获取一个随机聊天话题"""
    user_id = ctx.author.id
    
    # 🔧 【可自定义】AI生成话题的特殊提示词
    topic_prompt = "用户需要你给个聊天话题。请以游霄的语气给出一个可以聊天的话题，然后简单解释为什么想聊这个。"
    
    async with ctx.typing():
        response = await get_ai_response(topic_prompt, user_id)
    
    await ctx.send(response)

# 🔧 【可自定义】角色状态/心情 - AI生成版  
@bot.command(name=MOOD_COMMAND)
async def character_mood(ctx):
    """看看游霄现在什么状态"""
    user_id = ctx.author.id
    
    # 🔧 【可自定义】AI生成状态的特殊提示词
    mood_prompt = "用户问你现在什么状态/心情。请以游霄的语气描述你当前的状态，可以是暴躁、亢奋、不爽、嚣张等任意情绪，要符合游霄的人设。"
    
    async with ctx.typing():
        response = await get_ai_response(mood_prompt, user_id)
    
    await ctx.send(response)

# 🔧 【可自定义】帮助命令 - 纯文字版，游霄语气
@bot.command(name=INFO_COMMAND)
async def info_command(ctx):
    """查看所有可用命令"""
    
    # 🔧 【可自定义】游霄风格的帮助信息 - 使用自定义回复
    info_text = f"""我是赛车手，不是你的客服。

**命令列表：**
`{BOT_COMMAND_PREFIX}{CHAT_COMMAND_NAME} <消息>` - 想我就直接来找我。
`{BOT_COMMAND_PREFIX}{HISTORY_COMMAND}` - 就知道你记性不好，记录我留着呢。
`{BOT_COMMAND_PREFIX}{CLEAR_COMMAND}` - ……啧，删除记录。
`{BOT_COMMAND_PREFIX}{TOPIC_COMMAND}` - 没话找话也要聊？我给你找个话题？
`{BOT_COMMAND_PREFIX}{MOOD_COMMAND}` - 这么好奇我现在的状态？
`{BOT_COMMAND_PREFIX}{INFO_COMMAND}` - …我只给你当客服。

除了 `{BOT_COMMAND_PREFIX}{HISTORY_COMMAND}` 和 `{BOT_COMMAND_PREFIX}{CLEAR_COMMAND}`，其他命令都会用AI。有事说事，别浪费时间。"""
    
    await ctx.send(info_text)

# 🔧 【可自定义】启动信息配置 - 简化版
STARTUP_MESSAGES = {
    "missing_token": "❌ 请在config.py中设置正确的DISCORD_TOKEN！",
    "missing_api": "❌ 请在config.py中正确配置AI API！",
    "api_hint": "💡 需要设置 API_KEY 和 API_BASE_URL",
    "token_hint": "💡 在Discord开发者页面获取你的bot token",
    "api_success": "✅ 使用AI API: {}",
    "model_info": "🤖 模型: {}",
    "database_init": "🗄️ 初始化数据库...",
    "database_success": "✅ 数据库初始化完成",
    "bot_starting": "🚀 启动Discord bot...",
    "usage_hint": "💬 使用 {} 和{}聊天",
    "login_failed": "❌ Discord登录失败！请检查你的bot token是否正确",
    "startup_failed": "❌ 启动失败: {}"
}

if __name__ == "__main__":
    # 检查Discord配置
    if not DISCORD_TOKEN or DISCORD_TOKEN == "在这里填入你的discord_bot_token":
        print(STARTUP_MESSAGES["missing_token"])
        print(STARTUP_MESSAGES["token_hint"])
        exit(1)
    
    # 检查AI API配置（必需）
    if not API_KEY or not API_BASE_URL:
        print(STARTUP_MESSAGES["missing_api"])
        print(STARTUP_MESSAGES["api_hint"])
        exit(1)
    
    # 显示配置信息
    print(STARTUP_MESSAGES["api_success"].format(API_BASE_URL))
    print(STARTUP_MESSAGES["model_info"].format(API_MODEL))
    
    # 初始化数据库
    print(STARTUP_MESSAGES["database_init"])
    init_database()
    print(STARTUP_MESSAGES["database_success"])
    
    # 启动bot
    print(STARTUP_MESSAGES["bot_starting"])
    print(STARTUP_MESSAGES["usage_hint"].format(
        f"{BOT_COMMAND_PREFIX}{CHAT_COMMAND_NAME} <消息>", CHARACTER_NAME))
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print(STARTUP_MESSAGES["login_failed"])
    except Exception as e:
        print(STARTUP_MESSAGES["startup_failed"].format(e))

# 🔧 【总结】主要可自定义配置项（纯文字沉浸版）：
# 
# 1. 基础设置：
#    - BOT_COMMAND_PREFIX: 命令前缀 (默认'!')
#    - CHAT_HISTORY_LIMIT: AI记忆的对话条数 (已改为10)
#    - DATABASE_NAME: 数据库文件名
#    - CHAT_COMMAND_NAME: 聊天命令名 (默认'c')
#
# 2. AI API设置：
#    - AI_MAX_TOKENS: 回复长度 (默认300)
#    - AI_TEMPERATURE: 创造性0.0-2.0 (默认1.0)
#    - AI_REQUEST_TIMEOUT: 请求超时时间 (默认60秒)
#
# 3. 命令名称：
#    - CLEAR_COMMAND, HISTORY_COMMAND, TOPIC_COMMAND, MOOD_COMMAND, INFO_COMMAND
#
# 4. 显示设置：
#    - BOT_STATUS_TYPE: Bot活动类型
#    - BOT_STATUS_TEXT: Bot状态文字
#
# 5. 功能配置：
#    - HISTORY_LIMIT_DISPLAY: 历史显示条数 (默认10条)
#    - HISTORY_MESSAGE_PREVIEW: 消息预览字符数 (默认80字符)
#
# 6. AI提示词：
#    - topic_prompt: 话题生成提示词
#    - mood_prompt: 状态生成提示词
