"""
Marshal/PYC Converter Telegram Bot
Supports Python 3.6 - 3.13
Author: KhanhNguyen9872
"""

import os
import sys
import logging
import tempfile
import shutil
import subprocess
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for health check
app = Flask(__name__)

@app.route('/')
def health_check():
    return 'Bot is running!', 200

@app.route('/health')
def health():
    return {'status': 'healthy', 'bot': 'marshal_pyc_converter'}, 200

def run_flask():
    """Run Flask server for uptime monitoring"""
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Magic bytes for different Python versions
MAGIC_BYTES = {
    '3.6': b'3\r\r\n\x8bq\x98d\x0c\x00\x00\x00\xe3\x00\x00\x00',
    '3.7': b'B\r\r\n\x00\x00\x00\x00\x8bq\x98d\x0c\x00\x00\x00',
    '3.8': b'U\r\r\n\x00\x00\x00\x00\tq\x98d\x0b\x00\x00\x00',
    '3.9': b'a\r\r\n\x00\x00\x00\x00\tq\x98d\x0b\x00\x00\x00',
    '3.10': b'o\r\r\n\x00\x00\x00\x00\tq\x98d\x0b\x00\x00\x00',
    '3.11': b'\xa7\r\r\n\x00\x00\x00\x00\x04\x94\x90d\xd4`\x00\x00',
    '3.12': b'\xcb\r\r\n\x00\x00\x00\x00\tq\x98d\x0b\x00\x00\x00',
    '3.13': b'\xee\r\r\n\x00\x00\x00\x00*\x80\xb4e\x0b\x00\x00\x00'
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit

def get_magic(pyver):
    """Get magic bytes for Python version"""
    return MAGIC_BYTES.get(pyver, MAGIC_BYTES['3.11'])

def is_pyc_file(data):
    """Check if file is PYC format"""
    if len(data) < 4:
        return False
    return b"\r\r\n" in data[:4]

def convert_pyc_to_marshal(data, filename):
    """Convert PYC to Marshal format"""
    for i in range(1, 101):
        try:
            import marshal
            code_obj = marshal.loads(data[i:])
            if "<code object <module> at " in str(code_obj):
                marshal_code = data[i:]
                output = f"# Marshal/PYC by KhanhNguyen9872\n"
                output += f"# File name: [{filename}] (PYC -> Marshal)\n\n"
                output += f"exec(__import__('marshal').loads({marshal_code!r}),globals())"
                return output, f"{os.path.splitext(filename)[0]}_marshal.py"
        except:
            continue
    return None, None

def convert_marshal_to_pyc(data, filename):
    """Convert Marshal to PYC format"""
    import marshal
    import base64
    import zlib
    
    pyver = ".".join(sys.version.split(" ")[0].split(".")[:-1])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create hook file
        hook_path = os.path.join(tmpdir, 'khanhnguyen9872.py')
        hook_code = '''
if __name__=='__main__':
    try:__import__('os').unlink(__import__('sys').argv[0])
    except:pass
    try:__import__('os').unlink(__file__)
    except:pass
    try:__import__('os').unlink('khanhnguyen9872.py')
    except:pass
    __import__('sys').exit()
import marshal
from marshal import *
def loads(code,c="",b="",a=""):
    open('temp_marshal.pyc','wb').write(code)
    __import__('sys').exit(0)
'''
        
        compiled = compile(hook_code, '<KhanhNguyen9872>', 'exec')
        hook_bytes = base64.b64encode(zlib.compress(marshal.dumps(compiled)))[::-1]
        
        with open(hook_path, 'w') as f:
            f.write(f'exec(__import__("marshal").loads(__import__("zlib").decompress(__import__("base64").b64decode({hook_bytes!r}[::-1]))),globals())')
        
        # Create execution code
        exec_code = b'''
try:
    import khanhnguyen9872
    khanhnguyen9872.__spec__ = __import__('marshal').__spec__
    __import__('sys').modules['marshal']=__import__('sys').modules['khanhnguyen9872']
    __import__('marshal').loads.__module__ = 'marshal'
except:
    __import__('sys').exit(1)

''' + data
        
        compiled_exec = compile(exec_code, '<KhanhNguyen9872>', 'exec')
        exec_bytes = base64.b64encode(zlib.compress(marshal.dumps(compiled_exec)))[::-1]
        
        temp_code_path = os.path.join(tmpdir, 'temp_code.py')
        with open(temp_code_path, 'w') as f:
            f.write(f'exec(__import__("marshal").loads(__import__("zlib").decompress(__import__("base64").b64decode({exec_bytes!r}[::-1]))),globals())')
        
        # Execute
        try:
            subprocess.run(
                [sys.executable, temp_code_path],
                cwd=tmpdir,
                timeout=15,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
            
            marshal_pyc_path = os.path.join(tmpdir, 'temp_marshal.pyc')
            if os.path.exists(marshal_pyc_path):
                with open(marshal_pyc_path, 'rb') as f:
                    marshal_data = f.read()
                
                pyc_data = get_magic(pyver) + marshal_data
                return pyc_data, f"{os.path.splitext(filename)[0]}.pyc"
        except Exception as e:
            logger.error(f"Conversion error: {e}")
    
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_msg = """
*Hazy - Marshal/PYC Converter*

Convert between Marshal and PYC files (Python 3.6-3.13)

Send a file to convert. Max size: 50MB

/help - Instructions
/info - Bot details
"""
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_msg = """
*Help*

*Supported:* `.pyc` and `.py` (marshal) files

*Usage:*
Send file → Auto-detect format → Receive converted file

*Limits:* 50MB max, 15s timeout

Issues? Ensure file is valid Python bytecode.
"""
    await update.message.reply_text(help_msg, parse_mode='Markdown')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command"""
    pyver = ".".join(sys.version.split(" ")[0].split(".")[:-1])
    info_msg = f"""
*Bot Information*

*Runtime:* Python {pyver}
*Library:* python-telegram-bot 21.7
*Author:* KhanhNguyen9872
*Status:* ✅ Online 24/7
"""
    await update.message.reply_text(info_msg, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads"""
    document = update.message.document
    
    # Check file size
    if document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            "❌ File too large! Maximum size is 50MB."
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ Processing your file... Please wait."
    )
    
    try:
        # Download file
        file = await document.get_file()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=document.file_name) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name
        
        # Read file data
        with open(tmp_path, 'rb') as f:
            data = f.read()
        
        is_pyc = is_pyc_file(data)
        
        if is_pyc:
            # Convert PYC to Marshal
            await processing_msg.edit_text("🔄 Converting PYC to Marshal...")
            result, output_filename = convert_pyc_to_marshal(data, document.file_name)
            
            if result:
                output_path = os.path.join(tempfile.gettempdir(), output_filename)
                with open(output_path, 'w') as f:
                    f.write(result)
                
                await update.message.reply_document(
                    document=open(output_path, 'rb'),
                    filename=output_filename,
                    caption="✅ Converted: PYC → Marshal"
                )
                os.unlink(output_path)
            else:
                await processing_msg.edit_text("❌ Failed to convert PYC file. Invalid format?")
        else:
            # Convert Marshal to PYC
            await processing_msg.edit_text("🔄 Converting Marshal to PYC...")
            result, output_filename = convert_marshal_to_pyc(data, document.file_name)
            
            if result:
                output_path = os.path.join(tempfile.gettempdir(), output_filename)
                with open(output_path, 'wb') as f:
                    f.write(result)
                
                await update.message.reply_document(
                    document=open(output_path, 'rb'),
                    filename=output_filename,
                    caption="✅ Converted: Marshal → PYC"
                )
                os.unlink(output_path)
            else:
                await processing_msg.edit_text("❌ Failed to convert Marshal file. Invalid format?")
        
        # Cleanup
        os.unlink(tmp_path)
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await processing_msg.edit_text(
            f"❌ Error: {str(e)}\n\nPlease try again or contact support."
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    await update.message.reply_text(
        "Send a file to convert. Use /help for details."
    )

def main():
    """Start the bot"""
    # Get bot token from environment
    TOKEN = "8551227612:AAF0qLJ9L6GJVbi8ZIA9nGxw5kxj-RXeKwY"
    
    if not TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        sys.exit(1)
    
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask health check server started")
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Start bot
    logger.info("Bot started successfully!")
    print("=" * 63)
    print("🔥 HAZY - Marshal/PYC Converter Bot 🔥")
    print("=" * 63)
    print(f"Python Version: {sys.version.split()[0]}")
    print("Status: ✅ Running")
    print("Health Check: http://0.0.0.0:8080/health")
    print("=" * 63)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
