#!/bin/bash
# Скрипт для маршрутизации IP-адресов баз данных через wg0 (WireGuard)
# Файл со списком IP: ip_db.txt
# Использовать на сервере 1

IP_LIST_FILE="ip_db.txt"
WG_IFACE="wg0"

if [ ! -f "$IP_LIST_FILE" ]; then
    echo "Файл $IP_LIST_FILE не найден!"
    exit 1
fi

# Получаем gateway wg0 (адрес next-hop)
WG_GATEWAY=$(ip -4 addr show dev "$WG_IFACE" | awk '/inet / {print $2}' | cut -d'/' -f1)
if [ -z "$WG_GATEWAY" ]; then
    echo "Не удалось определить gateway для $WG_IFACE!"
    exit 2
fi

echo "Используется gateway $WG_GATEWAY для интерфейса $WG_IFACE"

while IFS= read -r ip; do
    # Пропускаем пустые строки и комментарии
    [[ -z "$ip" || "$ip" =~ ^# ]] && continue
    # Проверяем, есть ли уже маршрут
    if ip route show "$ip" | grep -q "$WG_IFACE"; then
        echo "Маршрут для $ip уже существует, пропускаем."
    else
        echo "Добавляю маршрут для $ip через $WG_IFACE ($WG_GATEWAY)"
        sudo ip route add "$ip" dev "$WG_IFACE" via "$WG_GATEWAY"
    fi
done < "$IP_LIST_FILE"

echo "Готово."
