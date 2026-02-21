import os
import sqlite3
import random
import requests
import logging
import subprocess
import signal
import sys
import json
import re
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv, set_key

# Пути
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(BASE_DIR / ".env")

SONNIK_DB = ROOT_DIR / "sonnik" / "sonnik_users.db"
NUMEROLOGY_DB = ROOT_DIR / "numerology" / "sonnik_users.db"
LOGS_DIR = ROOT_DIR / "logs"
TOKENS_CSV = ROOT_DIR / "Book1.csv"
INSTANCES_FILE = BASE_DIR / "instances.json"

# Базовые пресеты
PRESETS = {
    "sonnik_base1": {
        "name": "Сонник (Base 1)",
        "path": ROOT_DIR / "sonnik" / "bot_sonnik_base1.py",
        "working_dir": ROOT_DIR / "sonnik",
        "messages": ROOT_DIR / "sonnik" / "messages.json",
        "type": "sonnik"
    },
    "sonnik_base2": {
        "name": "Сонник (Base 2)",
        "path": ROOT_DIR / "sonnik" / "bot_sonnik_base2.py",
        "working_dir": ROOT_DIR / "sonnik",
        "messages": ROOT_DIR / "sonnik" / "messages.json",
        "type": "sonnik"
    },
    "numerology_base1": {
        "name": "Нумерология (Base 1)",
        "path": ROOT_DIR / "numerology" / "bot_number_base1.py",
        "working_dir": ROOT_DIR / "numerology",
        "messages": ROOT_DIR / "numerology" / "messages.json",
        "type": "numerology"
    },
    "numerology_base2": {
        "name": "Нумерология (Base 2)",
        "path": ROOT_DIR / "numerology" / "bot_number_base2.py",
        "working_dir": ROOT_DIR / "numerology",
        "messages": ROOT_DIR / "numerology" / "messages.json",
        "type": "numerology"
    },
    "sovmestimost_base1": {
        "name": "Совместимость (Base 1)",
        "path": ROOT_DIR / "sovmestimost" / "bot_sovmestimost_base1.py",
        "working_dir": ROOT_DIR / "sovmestimost",
        "messages": ROOT_DIR / "sovmestimost" / "messages.json",
        "type": "sovmestimost"
    },
    "sovmestimost_base2": {
        "name": "Совместимость (Base 2)",
        "path": ROOT_DIR / "sovmestimost" / "bot_sovmestimost_base2.py",
        "working_dir": ROOT_DIR / "sovmestimost",
        "messages": ROOT_DIR / "sovmestimost" / "messages.json",
        "type": "sovmestimost"
    },
    "admin": {
        "name": "Admin",
        "path": ROOT_DIR / "admin" / "bot_admin.py",
        "working_dir": ROOT_DIR / "admin",
        "messages": None,
        "type": "admin"
    }
}

# Конфигурация сообщений (мапинг типов на конфиги)
PRESET_TYPE_CONFIG = {
    "sonnik": {
        "welcome": "Приветственное сообщение (в меню)",
        "intro": "Интро при старте бота",
        "main_menu_button": "Кнопка главного меню",
        "buy_sparks_button": "Кнопка покупки искр",
        "back_button": "Кнопка Назад",
        "interpret_another_button": "Кнопка Расшифровать еще один сон",
        "quick_topup_button": "Кнопка быстрой покупки",
        "describe_dream_prompt": "Текст Опишите ваш сон",
        "numerology_unavailable": "Сообщение о недоступности нумерологии",
        "prompt_name": "Запрос имени",
        "prompt_birthdate": "Запрос даты рождения",
        "thinking": "Фразы при ожидании (список)",
        "dream_request_messages": "Фразы после первого сна (список)",
        "start_messages": "Приветствия (список)",
        "back_to_menu_msg": "Текст возврата в меню"
    },
    "numerology": {
        "welcome": "Приветственное сообщение",
        "choose_language": "Текст выбора языка",
        "main_menu": "Кнопка главного меню",
        "buy_sparks": "Кнопка покупки искр",
        "prompt_name": "Запрос имени",
        "prompt_birthdate": "Запрос даты рождения",
        "thinking": "Фразы при ожидании (список)",
        "report_ready": "Отчет готов",
        "report_error": "Ошибка отчета",
        "sparks_deducted": "Списание искр",
        "insufficient_sparks": "Недостаточно искр",
        "back": "Кнопка Назад",
        "learn_more": "Кнопка Узнать больше",
        "purchase_title": "Заголовок покупки",
        "payment_waiting": "Ожидание оплаты",
        "check_payment": "Кнопка проверки оплаты",
        "i_paid": "Кнопка Я оплатил",
        "payment_success": "Успешная оплата",
        "payment_already": "Оплата уже была",
        "payment_pending": "Платеж в обработке",
        "payment_error": "Ошибка платежа",
        "invalid_name": "Неверное имя",
        "invalid_date": "Неверная дата",
        "user_not_found": "Пользователь не найден",
        "numerology_req_messages": "Доп. сообщения после первого отчета (список)",
        "back_to_menu_msg": "Текст возврата в меню"
    },
    "sovmestimost": {
        "welcome": "Приветственное сообщение (в меню)",
        "intro": "Интро при старте бота",
        "main_menu_button": "Кнопка главного меню",
        "option_names_dates": "Кнопка: Имена + даты рождения (углубленный разбор)",
        "option_names_only": "Кнопка: Имена",
        "buy_sparks_button": "Кнопка покупки искр",
        "back_button": "Кнопка Назад",
        "interpret_another_button": "Кнопка Узнать еще раз",
        "quick_topup_button": "Кнопка быстрой покупки",
        "describe_dream_prompt": "Текст запроса данных о паре",
        "prompt_names_dates": "Текст запроса имен и дат рождения",
        "prompt_names_dates_name1": "Текст запроса первого имени (для опции имена+даты)",
        "prompt_names_dates_date1": "Текст запроса первой даты рождения",
        "prompt_names_dates_name2": "Текст запроса второго имени (для опции имена+даты)",
        "prompt_names_dates_date2": "Текст запроса второй даты рождения",
        "prompt_names_only": "Текст запроса только имен",
        "prompt_find_pair": "Текст запроса для поиска пары",
        "prompt_name1": "Текст запроса первого имени",
        "prompt_name2": "Текст запроса второго имени",
        "prompt_names_dates_ai": "Промпт для ИИ: углубленный разбор (имена+даты)",
        "prompt_names_only_ai": "Промпт для ИИ: анализ по именам",
        "prompt_find_pair_ai": "Промпт для ИИ: поиск подходящей пары",
        "invalid_names_dates_format": "Сообщение об ошибке формата имен и дат",
        "invalid_date_format": "Сообщение об ошибке формата даты",
        "error_missing_data": "Сообщение об ошибке отсутствия данных",
        "thinking": "Фразы при ожидании (список)",
        "start_messages": "Приветствия (список)",
        "back_to_menu_msg": "Текст возврата в меню",
        "insufficient_sparks": "Недостаточно искр",
        "sparks_deducted_msg": "Сообщение о списании искр",
        "ai_error": "Ошибка ИИ",
        "payment_waiting": "Ожидание оплаты",
        "payment_success": "Успешная оплата",
        "purchase_title": "Заголовок покупки"
    },
    "admin": {}
}

app = FastAPI(title="Bot Manager Admin")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# --- Хелперы для токенов ---
def load_available_tokens():
    tokens = []
    if not TOKENS_CSV.exists():
        return tokens
    try:
        with open(TOKENS_CSV, mode='r', encoding='utf-8-sig') as f:
            # Сначала читаем одну строку, чтобы определить разделитель
            first_line = f.readline()
            f.seek(0)
            delimiter = ';' if ';' in first_line else ','
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Очищаем ключи от BOM, пробелов и приводим к нижнему регистру для надежности
                clean_row = {str(k).strip().lower(): v for k, v in row.items() if k}
                # Но для шаблона нам нужны оригинальные ключи или фиксированные
                # Давайте сделаем фиксированные ключи: token, comment, link
                final_row = {
                    "token": clean_row.get("token", ""),
                    "comment": clean_row.get("comment", ""),
                    "link": clean_row.get("proper_link", "") or clean_row.get("link", "")
                }
                if final_row["token"]:
                    tokens.append(final_row)
    except Exception as e:
        logger.error(f"Error loading tokens: {e}")
    return tokens

def save_available_tokens(tokens: List[dict]):
    if not tokens: return
    try:
        keys = tokens[0].keys()
        with open(TOKENS_CSV, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys, delimiter=';')
            writer.writeheader()
            writer.writerows(tokens)
    except Exception as e:
        logger.error(f"Error saving tokens: {e}")

# --- Хелперы для инстансов ---
def load_instances() -> Dict:
    if not INSTANCES_FILE.exists():
        # Токены хранятся только в instances.json (файл в .gitignore). Скопируйте instances.json.example в instances.json и заполните.
        return {}
    with open(INSTANCES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_instances(instances: Dict):
    with open(INSTANCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(instances, f, ensure_ascii=False, indent=2)

# --- Процесс Хелперы ---
def get_running_status():
    cmd = 'powershell "Get-CimInstance Win32_Process -Filter \\"name=\'python.exe\'\\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"'
    running = {} # token -> list of pids
    
    try:
        output = subprocess.check_output(cmd, shell=True, text=True).strip()
        if output:
            processes = json.loads(output)
            if isinstance(processes, dict): processes = [processes]
            for proc in processes:
                cmd_line = proc.get("CommandLine", "")
                pid = proc.get("ProcessId")
                if not cmd_line or not pid: continue
                
                # Ищем токен в командной строке
                match = re.search(r'--token\s+([\d\w:]+)', cmd_line)
                if match:
                    token = match.group(1)
                    if token not in running: running[token] = []
                    running[token].append(str(pid))
    except Exception as e:
        logger.error(f"Error checking processes: {e}")
    return running

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request, token: Optional[str] = None):
    if token != ADMIN_TOKEN: return HTMLResponse("Unauthorized", status_code=401)
    
    instances = load_instances()
    running_map = get_running_status()
    available_tokens = load_available_tokens()
    
    # Формируем данные для отображения
    display_bots = []
    for bot_id, info in instances.items():
        token_val = info["token"]
        is_running = token_val in running_map
        display_bots.append({
            "id": bot_id,
            "name": bot_id,
            "comment": info["comment"],
            "status": "Running" if is_running else "Stopped",
            "token": token_val,
            "link": info.get("link", ""),
            "preset": info["preset"],
            "is_test": info.get("is_test", False),
            "fixed_lang": info.get("fixed_lang")
        })

    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "token": token,
        "bots": display_bots,
        "available_tokens": available_tokens,
        "presets": PRESETS
    })

@app.get("/admin/bot/{bot_id}", response_class=HTMLResponse)
async def bot_settings(request: Request, bot_id: str, token: str, lang: str = "ru"):
    if token != ADMIN_TOKEN: return HTMLResponse("Unauthorized", status_code=401)
    
    instances = load_instances()
    if bot_id not in instances:
        return RedirectResponse(f"/admin?token={token}")
    
    bot_info = instances[bot_id]
    preset_id = bot_info["preset"]
    
    # Fallback для старых названий пресетов
    if preset_id == "sonnik": preset_id = "sonnik_base1"
    if preset_id == "numerology": preset_id = "numerology_base1"
    
    if preset_id not in PRESETS:
        return RedirectResponse(f"/admin?token={token}")
        
    preset_data = PRESETS[preset_id]
    preset_type = preset_data["type"]
    
    # Загружаем сообщения
    msg_path = preset_data["messages"]
    if msg_path and msg_path.exists():
        with open(msg_path, "r", encoding='utf-8') as f:
            all_messages = json.load(f)
    else:
        all_messages = {"ru": {}, "en": {}, "es": {}}

    # Загружаем ключи из .env
    env_path = ROOT_DIR / preset_type / ".env"
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding='utf-8') as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    config = PRESET_TYPE_CONFIG.get(preset_type, {})
    
    return templates.TemplateResponse("admin/bot_settings.html", {
        "request": request,
        "token": token,
        "bot_id": bot_id,
        "bot_info": bot_info,
        "all_messages": all_messages,
        "config": config,
        "current_lang": lang,
        "preset_id": preset_id,
        "presets": PRESETS,
        "is_clone": bot_id.startswith("clone_"),
        "env_vars": env_vars,
        "is_admin_bot": preset_type == "admin"
    })

@app.get("/admin/bot/delete")
@app.get("/admin/bot/action")
@app.get("/admin/bot/clone")
@app.get("/admin/bot/update")
async def redirect_to_admin(token: Optional[str] = None):
    return RedirectResponse(f"/admin?token={token or ADMIN_TOKEN}")

@app.post("/admin/bot/clone")
async def clone_bot(token: str = Form(...), preset: str = Form(...), selected_token: str = Form(...), 
                    is_test: bool = Form(False), fixed_lang: str = Form("auto")):
    if token != ADMIN_TOKEN: raise HTTPException(401)
    
    instances = load_instances()
    
    # Проверка: не используется ли уже этот токен
    for inst_id, inst_info in instances.items():
        if inst_info["token"] == selected_token:
            # Можно вернуть ошибку или просто перенаправить обратно с уведомлением (в данном случае просто редирект)
            return RedirectResponse(f"/admin?token={token}&error=token_in_use", status_code=303)

    available = load_available_tokens()
    target = next((t for t in available if t["token"] == selected_token), None)
    if not target: raise HTTPException(400, "Token not found")
    
    new_id = f"clone_{selected_token.split(':')[0]}"
    
    instances[new_id] = {
        "preset": preset,
        "token": selected_token,
        "comment": target["comment"],
        "link": target.get("link", ""),
        "is_test": is_test,
        "fixed_lang": fixed_lang
    }
    save_instances(instances)
    return RedirectResponse(f"/admin?token={token}", status_code=303)

@app.post("/admin/bot/delete")
async def delete_bot(bot_id: str = Form(...), token: str = Form(...)):
    if token != ADMIN_TOKEN: raise HTTPException(401)
    
    # Не разрешаем удалять основных ботов (на всякий случай)
    if bot_id in ["bot_number", "bot_sonnik", "bot_admin"]:
        raise HTTPException(400, "Cannot delete core bots")
        
    instances = load_instances()
    if bot_id in instances:
        # Сначала останавливаем бота, если он запущен
        bot_info = instances[bot_id]
        bot_token = bot_info["token"]
        running = get_running_status()
        pids = running.get(bot_token, [])
        for pid in pids:
            subprocess.run(['taskkill', '/F', '/T', '/PID', pid], shell=True, capture_output=True)
            
        del instances[bot_id]
        save_instances(instances)
        
    return RedirectResponse(f"/admin?token={token}", status_code=303)

@app.post("/admin/bot/action")
async def bot_action(bot_id: str = Form(...), action: str = Form(...), token: str = Form(...)):
    if token != ADMIN_TOKEN: raise HTTPException(401)
    
    instances = load_instances()
    if bot_id not in instances: raise HTTPException(404)
    
    bot_info = instances[bot_id]
    preset_id = bot_info["preset"]
    
    # Fallback для старых названий пресетов
    if preset_id == "sonnik": preset_id = "sonnik_base1"
    if preset_id == "numerology": preset_id = "numerology_base1"
    
    if preset_id not in PRESETS:
        logger.error(f"Preset {preset_id} not found for bot {bot_id}")
        return RedirectResponse(f"/admin?token={token}&error=preset_not_found")
        
    preset = PRESETS[preset_id]
    bot_token = bot_info["token"]
    is_test = bot_info.get("is_test", False)
    fixed_lang = bot_info.get("fixed_lang")

    if action == "start":
        args_list = [sys.executable, str(preset["path"]), "--token", bot_token, "--messages", str(preset["messages"])]
        if is_test:
            args_list.append("--test")
        if fixed_lang and fixed_lang != "auto":
            args_list.extend(["--lang", fixed_lang])
            
        subprocess.Popen(args_list, cwd=str(preset["working_dir"]), 
                         creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
    
    elif action == "stop":
        running = get_running_status()
        pids = running.get(bot_token, [])
        for pid in pids:
            subprocess.run(['taskkill', '/F', '/T', '/PID', pid], shell=True, capture_output=True)

    return RedirectResponse(f"/admin?token={token}", status_code=303)

@app.post("/admin/bot/update")
async def update_bot_config(request: Request, bot_id: str = Form(...), token: str = Form(...), 
                            new_token: str = Form(...), new_comment: str = Form(...), 
                            new_link: str = Form(...), preset: str = Form(...),
                            is_test: bool = Form(False), fixed_lang: str = Form("auto"), 
                            lang: str = Form("ru")):
    if token != ADMIN_TOKEN: raise HTTPException(401)
    
    instances = load_instances()
    if bot_id not in instances: raise HTTPException(404)
    
    # Для admin-бота не меняем пресет
    bot_info = instances[bot_id]
    current_preset = bot_info.get("preset")
    if current_preset == "admin":
        preset = "admin"
    
    instances[bot_id]["token"] = new_token
    instances[bot_id]["comment"] = new_comment
    instances[bot_id]["link"] = new_link
    instances[bot_id]["preset"] = preset
    instances[bot_id]["is_test"] = is_test
    instances[bot_id]["fixed_lang"] = fixed_lang
    save_instances(instances)
    
    form_data = await request.form()
    
    # Обновление .env файла
    bot_info = instances[bot_id]
    preset_data = PRESETS[bot_info["preset"]]
    preset_type = preset_data["type"]
    env_path = ROOT_DIR / preset_type / ".env"
    is_clone = bot_id.startswith("clone_")
    
    if env_path.exists():
        with open(env_path, "r", encoding='utf-8') as f:
            lines = f.readlines()
        
        updated_keys = {
            "TELEGRAM_BOT_TOKEN": new_token if not is_clone else None,
            "YOOKASSA_SHOP_ID_TEST": form_data.get("yookassa_shop_id_test"),
            "YOOKASSA_SECRET_KEY_TEST": form_data.get("yookassa_secret_key_test")
        }
        
        new_lines = []
        handled_keys = set()
        for line in lines:
            if "=" in line:
                k = line.split("=", 1)[0].strip()
                if k in updated_keys and updated_keys[k] is not None:
                    new_lines.append(f"{k}={updated_keys[k]}\n")
                    handled_keys.add(k)
                    continue
            new_lines.append(line)
            
        for k, v in updated_keys.items():
            if k not in handled_keys and v is not None:
                new_lines.append(f"{k}={v}\n")
                
        with open(env_path, "w", encoding='utf-8') as f:
            f.writelines(new_lines)

    # Обновление сообщений
    msg_path = preset_data["messages"]
    if msg_path.exists():
        with open(msg_path, "r", encoding='utf-8') as f: msgs = json.load(f)
    else: msgs = {"ru": {}, "en": {}, "es": {}}

    if lang not in msgs: msgs[lang] = {}

    for key in PRESET_TYPE_CONFIG[preset_type]:
        val = form_data.get(f"msg_{key}")
        if val is not None:
            if "(список)" in PRESET_TYPE_CONFIG[preset_type][key]:
                try: msgs[lang][key] = json.loads(val)
                except: msgs[lang][key] = [s.strip() for s in val.split("\n") if s.strip()]
            else: msgs[lang][key] = val

    with open(msg_path, "w", encoding='utf-8') as f:
        json.dump(msgs, f, ensure_ascii=False, indent=2)

    return RedirectResponse(f"/admin/bot/{bot_id}?token={token}&lang={lang}", status_code=303)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
