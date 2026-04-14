# Telegram Bot для управления WireGuard маршрутами (S2)

Simple Telegram bot для управления доменами и IP-адресами в WireGuard через SSH.

## Архитектура

```
Telegram (пользователь)
    ↓
Bot на S2
    ├─ Резолв домена (dig/dnspython)
    ├─ SSH на S1
    │   ├─ echo IP >> wg_destinations.txt
    │   └─ awg-quick down/up (по команде /restart)
    └─ Результат обратно в Telegram
```

## Установка

### 1. Настройка SSH ключа (на S2)

Если еще нет SSH ключа:
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
```

Добавить публичный ключ на S1:
```bash
# На S1:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
cat >> ~/.ssh/authorized_keys << EOF
your_public_key_from_S2
EOF
chmod 600 ~/.ssh/authorized_keys
```

### 2. Установить зависимости на S2

```bash
cd tg_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Конфигурация

Скопируй `.env.example` в `.env`:
```bash
cp .env.example .env
```

Отредактируй `.env`:
```bash
# Получить токен: https://t.me/BotFather
TELEGRAM_BOT_TOKEN=your_bot_token_here

# SSH параметры S1
SSH_HOST=s1.example.com
SSH_PORT=22
SSH_USER=wg_bot
SSH_KEY_PATH=/home/user/.ssh/id_rsa

# Пути на S1 (относительно домашней директории пользователя)
S1_WG_DESTINATIONS_PATH=wg_destinations.txt
S1_WG_V6_ROUTES_PATH=wg_v6_routes.txt
S1_UPDATE_SCRIPT_PATH=/path/to/update_allowedips_awg.sh

# DNS
DNS_TIMEOUT=5
DNS_SERVER=8.8.8.8

# Опционально: ограничить доступ одним пользователем
ADMIN_USER_ID=your_telegram_id
```

Получить свой Telegram ID: напишите боту `@userinfobot` → он вернет ваш ID.

### 4. Запуск бота

```bash
cd tg_bot
source venv/bin/activate
python3 bot.py
```

## Использование

### Команды

| Команда | Описание |
|---------|---------|
| `/start` | Справка и основная информация |
| `/help` | Подробная справка |
| **домен.рф** или `/add домен.рф` | Резолвить домен и добавить IP |
| `/status` | Показать текущий список IP в wg_destinations.txt |
| `/restart` | Перезапустить туннель (применить AllowedIPs) |
| `/clear` | Отменить ожидающие домены (текущая сессия) |

### Пример использования

1. Отправить боту: `example.com`
   → Бот резолвит и добавляет IP в wg_destinations.txt

2. Отправить боту: `google.com`
   → Еще один домен, еще IP

3. Отправить боту: `/status`
   → Показывает все IP в файле

4. Отправить боту: `/restart`
   → Перезапускает туннель (выполняет `awg-quick down/up`)

## Особенности

- ✅ Асинхронный бот (aiogram)
- ✅ SSH с аутентификацией по ключу (paramiko)
- ✅ Резолв IPv4 и IPv6 (dnspython)
- ✅ Конфирмация перед перезапуском
- ✅ Опциональное ограничение доступа (ADMIN_USER_ID)
- ✅ Логирование ошибок
- ✅ Timeout на DNS запросы

## Безопасность

⚠️ **SSH ключ на S1**

Рекомендуется ограничить команды, которые может выполнить ключ бота:

На S1 в `~/.ssh/authorized_keys` используй `command=` опцию:
```
command="if [[ \"$SSH_ORIGINAL_COMMAND\" =~ ^(echo|awg-quick|cat).* ]]; then exec $SSH_ORIGINAL_COMMAND; else echo 'Command not allowed'; exit 1; fi",restrict ssh-rsa AAAA... wg_bot@s2
```

Но это сложновато. Минимум:
- Используй отдельного пользователя `wg_bot` на S1
- Дай ему права только на изменение файлов в проекте
- Используй SSH ключ без пароля, но с ограничениями

## Логирование

Логи выводятся в stdout. Для продакшена используй systemd сервис или supervisor.

## Troubleshooting

**Bot doesn't respond:**
- Проверь `TELEGRAM_BOT_TOKEN` в `.env`
- Проверь интернет соединение

**SSH connection failed:**
- Проверь доступность S1: `ssh -i ~/.ssh/id_rsa user@s1.host`
- Проверь пути в `.env`
- Проверь права на файлы

**DNS resolution fails:**
- Проверь `DNS_SERVER` в `.env`
- Проверь доступ в интернет на S2

## Развертывание (systemd)

Создай файл `/etc/systemd/system/tg-wg-bot.service`:

```ini
[Unit]
Description=Telegram WireGuard Bot (S2)
After=network.target

[Service]
Type=simple
User=bot_user
WorkingDirectory=/path/to/wg_routes/tg_bot
Environment="PATH=/path/to/wg_routes/tg_bot/venv/bin"
ExecStart=/path/to/wg_routes/tg_bot/venv/bin/python3 bot.py
Restart=on-failure
RestartSec=10

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tg-wg-bot
sudo systemctl status tg-wg-bot
```

## Структура проекта

```
tg_bot/
  ├── bot.py              # Основной бот (aiogram)
  ├── config.py           # Конфиг из .env
  ├── dns_resolver.py     # Резолв доменов
  ├── ssh_handler.py      # SSH операции
  ├── requirements.txt    # Зависимости
  ├── .env                # Конфиг (не в git!)
  ├── .env.example        # Шаблон конфига
  └── README.md           # Этот файл
```
