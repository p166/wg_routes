#!/bin/bash
# Добавляет служебный IP (например, DNS) в AllowedIPs WireGuard-конфига wg0.conf
# Использование: ./add_dns_to_allowedips.sh 10.8.1.1

WG_CONF="/etc/amnezia/amneziawg/wg0.conf"
WG_IFACE="wg0"
AWG_CTRL="awg-quick"
DNS_IP="$1"

if [ -z "$DNS_IP" ]; then
    echo "Укажите IP DNS-сервера, например: $0 10.8.1.1"
    exit 1
fi

if [ ! -f "$WG_CONF" ]; then
    echo "Файл $WG_CONF не найден!"
    exit 2
fi

# Проверяем, есть ли уже этот IP в AllowedIPs
if grep -q "AllowedIPs" "$WG_CONF" | grep -q "$DNS_IP"; then
    echo "IP $DNS_IP уже есть в AllowedIPs."
    exit 0
fi

# Добавляем IP к AllowedIPs
cp "$WG_CONF" "$WG_CONF.bak.$(date +%s)"
sed -i "/^AllowedIPs[ ]*=.*/{h;s/$/, $DNS_IP\/32/};
        t;${x;/^$/!{s/$/, $DNS_IP\/32/;p}}" "$WG_CONF"
echo "Добавлен $DNS_IP/32 в AllowedIPs в $WG_CONF."

# Перезапуск интерфейса
$AWG_CTRL down $WG_IFACE && $AWG_CTRL up $WG_IFACE
if [ $? -eq 0 ]; then
    echo "Интерфейс $WG_IFACE успешно перезапущен."
else
    echo "Ошибка при перезапуске $WG_IFACE! Проверьте логи."
    exit 3
fi
