import asyncio
import os
import glob
import uuid
import subprocess
import yt_dlp
import imageio_ffmpeg
from dotenv import load_dotenv

# Настройка путей для FFmpeg
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG_DIR = os.path.dirname(FFMPEG_EXE)
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

TEMP_DIR = os.path.abspath("temp_processing")
os.makedirs(TEMP_DIR, exist_ok=True)

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

load_dotenv("short.env")
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- КРАСИВОЕ ПРИВЕТСТВИЕ С КНОПКАМИ ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    # Создаем интерактивные кнопки под сообщением
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 Как пользоваться?", callback_data="help_info")
            ],
            [
                InlineKeyboardButton(text="⭐ Поддерживаемые сервисы", callback_data="services_info")
            ]
        ]
    )

    text = (
        "<b>👋 Добро пожаловать в SHORTS CONVERTER!</b>\n\n"
        "Я помогу тебе моментально превратить любое горизонтальное видео в <b>вертикальный Shorts / Reel / TikTok 9:16</b> с размытым фоном!\n\n"
        "<b>🚀 Быстрый старт:</b>\n"
        "Просто отправь мне ссылку на видео из <b>YouTube</b> или <b>VK Видео</b>.\n\n"
        "<code>⚡ Время обработки: 1-2 минуты</code>\n"
        "<code>⏱ Максимальная длина: 4.5 минуты</code>"
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# Обработка нажатий на инлайн-кнопки
@dp.callback_query(F.data == "help_info")
async def process_help(callback: types.CallbackQuery):
    await callback.message.answer(
        "<b>📖 Инструкция по использованию:</b>\n\n"
        "1. Скопируй ссылку на нужное видео.\n"
        "2. Вставь и отправь ссылку в этот чат.\n"
        "3. Дождись окончания конвертации и скачай готовый Shorts (9:16)!\n\n"
        "💡 <i>Совет: Бот автоматически оставляет 4.5 минуты от начала ролика и сжимает файл для Telegram.</i>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "services_info")
async def process_services(callback: types.CallbackQuery):
    await callback.message.answer(
        "<b>🌐 Поддерживаемые платформы:</b>\n\n"
        "• <b>YouTube</b> (обычные видео и ролика с ru/us)\n"
        "• <b>VK Видео</b> (vk.com и vkvideo.ru)",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# --- ОБРАБОТКА ССЫЛОК ---
@dp.message(F.text.regexp(r'(https?://)?(www\.)?(youtube\.com|youtu\.be|vk\.com|vkvideo\.ru)/.+'))
async def handle_video_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("⚡ <b>Скачиваю видео...</b>", parse_mode=ParseMode.HTML)
    
    unique_id = str(uuid.uuid4())[:8]
    input_file = os.path.join(TEMP_DIR, f"input_{unique_id}.mp4")
    output_file = os.path.join(TEMP_DIR, f"shorts_{unique_id}.mp4")
    
    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'outtmpl': input_file,
        'overwrites': True,
        'quiet': True,
        'nocheckcertificate': True,
        'ffmpeg_location': FFMPEG_EXE,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'source_address': '0.0.0.0',
    }   
    
    try:
        loop = asyncio.get_event_loop()
        
        def download_media():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, download_media)
        
        downloaded = glob.glob(os.path.join(TEMP_DIR, f"input_{unique_id}.*"))
        if not downloaded:
            raise Exception("Не удалось скачать видео. Проверьте ссылку.")
        real_input = downloaded[0]

        await status_msg.edit_text("⚡ <b>Конвертирую в формат Shorts 9:16 (4.5 мин)...</b>", parse_mode=ParseMode.HTML)
        
        def process_with_ffmpeg():
            filter_complex = (
                "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20:5[bg];"
                "[0:v]scale=720:-1[fg];"
                "[bg][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
            )
            
            cmd = [
                FFMPEG_EXE,
                '-y',
                '-ss', '00:00:00',
                '-t', '00:04:30',
                '-i', real_input,
                '-filter_complex', filter_complex,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-b:v', '1000k',
                '-c:a', 'aac',
                '-b:a', '96k',
                output_file
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                print(f"FFmpeg Error: {result.stderr}")
                raise Exception("Ошибка при конвертации видео.")

        await loop.run_in_executor(None, process_with_ffmpeg)
        
        await status_msg.edit_text("📤 <b>Отправляю готовый файл...</b>", parse_mode=ParseMode.HTML)
        video_to_send = FSInputFile(output_file)
        await message.answer_video(video=video_to_send, caption="🎬 <b>Ваш Shorts 9:16 готов!</b>", parse_mode=ParseMode.HTML)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Произошла ошибка:</b> {e}", parse_mode=ParseMode.HTML)
        
    finally:
        for temp_f in glob.glob(os.path.join(TEMP_DIR, f"*{unique_id}*")):
            if os.path.exists(temp_f):
                try:
                    os.remove(temp_f)
                except Exception:
                    pass

async def main():
    print(">>> БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
