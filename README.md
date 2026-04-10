# wg_routes

Набор скриптов для подготовки и применения маршрутов через WireGuard/AmneziaWG на Linux.

Сценарий позволяет:
- читать единый входной список доменов и IP/подсетей;
- резолвить домены в IPv4;
- формировать отдельные файлы маршрутов IPv4 и IPv6;
- применять маршруты, iptables-правила и базовые сетевые настройки.

## Состав проекта

- `update_wg_routes.sh` — основной скрипт обновления и применения маршрутов.
- `install_awg.sh` — установка и запуск AmneziaWG (пример для Ubuntu/Debian).
- `Ruantiblock.input` — входной список доменов/IP/подсетей.
- `list_domains.txt` — сгенерированный список доменов.
- `list_ips.txt` — сгенерированный список IP/подсетей.
- `wg_destinations.txt` — итоговый IPv4-список для маршрутов WG.
- `wg_v6_routes.txt` — итоговый IPv6-список для маршрутов WG.
- `wg_bypass_routes.txt` — IPv4-подсети, которые идут через основной шлюз (минуя WG).
- `list_failed_domains.txt` — домены, которые не удалось зарезолвить.
- `wg_update.log` — лог работы (если включить редирект в скрипте).

## Требования

- Linux с установленными утилитами:
  - `ip` (iproute2)
  - `iptables`
  - `dig` (обычно пакет dnsutils)
  - `wg`/`awg` (для WireGuard/AmneziaWG)
- Права root для применения маршрутов и firewall-правил.

## Быстрый старт

1. Заполните `Ruantiblock.input`.
2. Сделайте скрипт исполняемым:
   - `chmod +x update_wg_routes.sh`
3. Запустите в нужном режиме:
   - `sudo ./update_wg_routes.sh` — режим `all` (обновить + применить)
   - `sudo ./update_wg_routes.sh update` — только обновить списки
   - `sudo ./update_wg_routes.sh apply` — только применить маршруты

## Формат входного файла

Файл `Ruantiblock.input` поддерживает:
- домены: `example.com`
- wildcard-домены: `*.example.com`
- IPv4: `1.2.3.4` или `1.2.3.0/24`
- IPv6: `2001:db8::/32`
- комментарии: строки, начинающиеся с `#`

Примечания:
- URL в формате `https://...` поддерживаются: скрипт автоматически извлекает hostname.
- Записи вида `hostname/path` также нормализуются до `hostname`.
- Для wildcard запись очищается до базового домена при DNS-резолве.

## Настройка сети

В `update_wg_routes.sh` есть ключевые переменные:
- `AUTO_DETECT_NETWORK=1` — автоопределение интерфейсов/шлюза.
- `WG_IFACE`, `ETH_IFACE`, `GATEWAY`, `WG_V6_GATEWAY` — можно задать вручную через переменные окружения.
- `BYPASS_V4=wg_bypass_routes.txt` — файл исключений: эти IPv4-подсети пойдут через `GATEWAY`, а не через WG.
- `ENABLE_UPDATE` и `ENABLE_APPLY` — включение/выключение этапов.

Пример ручного запуска с переопределением:
- `sudo WG_IFACE=wg0 ETH_IFACE=eth0 GATEWAY=192.168.10.1 ./update_wg_routes.sh all`

## Осторожно

Скрипт:
- меняет default route;
- включает IPv4 forwarding;
- изменяет правила iptables.

Запускайте на хосте, где понимаете текущую сетевую схему, и по возможности сначала тестируйте в `update` режиме.

Чтобы хост действительно работал как шлюз для других устройств LAN:
- на клиентах должен быть выставлен default gateway = IP этого хоста в LAN (или через DHCP);
- этот хост должен иметь доступ в интернет через `ETH_IFACE` и активный интерфейс `WG_IFACE`.

### Исключения из WG (маршрутизация через основной шлюз)

Добавьте нужные IPv4-сети в файл `wg_bypass_routes.txt`.

Поддерживаются форматы:
- `1.2.3.4` (будет воспринят как `1.2.3.4/32`)
- `1.2.3.0/24`
- пустые строки и комментарии `#` игнорируются

Для этих подсетей скрипт установит маршрут:
- `via GATEWAY dev ETH_IFACE`

Эти bypass-маршруты применяются отдельно и принудительно, даже если подсети нет в `wg_destinations.txt`.

Важно: запись вроде `10.3.3.0/16` будет нормализована до сети `10.3.0.0/16`.

Все остальные подсети из `wg_destinations.txt` будут отправляться через `WG_IFACE`.

### Проверка после apply

После применения маршрутов быстро проверьте, куда реально идет трафик:

```bash
ip route get 10.3.3.200
ip route | grep 10.3
iptables -S FORWARD
```

Если для целевой подсети видите маршрут `via GATEWAY dev ETH_IFACE`, bypass работает.

## Установка AmneziaWG

Скрипт `install_awg.sh`:
- копирует конфиг в `/etc/amnezia/amneziawg/wg0.conf`;
- устанавливает пакет `amneziawg`;
- применяет конфиг и включает сервис `awg-quick@wg0`.

Перед запуском проверьте, что локально есть файл `~/amnezia_for_awg.conf`.

## Подготовка конфига AWG

## Получаем файл подключения из приложения AmneziaVPN в формате native AWG

или

## Можно конвертировать формат `vpn://` в `wg.conf`

```bash
git clone https://github.com/p166/config-decoder.git
cd config-decoder
git checkout feature/render-wg-config-view
```

Из итогового файла обязательно удаляем строки:
- `DNS`
- `I1`
- `I2`
- `I3`
- `I4`
- `I5`

## Веб-админка (Flask)

Добавлен минимальный веб-интерфейс в каталоге `webadmin`.

Что умеет:
- редактировать `Ruantiblock.input`;
- редактировать `wg_bypass_routes.txt`;
- запускать `update_wg_routes.sh` в режимах `all|update|apply`;
- запускать `install_awg.sh`;
- показывать только статус `running|ok|fail` и статистику, извлеченную из лога.

### Быстрый запуск

```bash
cd webadmin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

По умолчанию веб-интерфейс доступен на `http://0.0.0.0:8081`.

### Примечания

- Параллельные запуски скриптов блокируются lock-файлом `.wg_routes_admin.lock`.
- Логи запусков пишутся в каталог `webadmin_logs`.
- Для выполнения сетевых действий скриптов запускайте приложение с правами root.

### Запуск через systemd

В каталоге `webadmin` есть шаблон сервиса `wg-routes-webadmin.service`.

```bash
sudo cp webadmin/wg-routes-webadmin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wg-routes-webadmin.service
sudo systemctl status wg-routes-webadmin.service
```
