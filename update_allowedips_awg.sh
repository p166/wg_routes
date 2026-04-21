#!/bin/bash
# Автоматическое обновление AllowedIPs для awg (amneziawg) и перезапуск wg0
# Использует wg_destinations.txt для генерации списка AllowedIPs
# Использование: ./update_allowedips_awg.sh

WG_CONF="/etc/amnezia/amneziawg/wg0.conf"
WG_DEST="/etc/amnezia/amneziawg/wg_destinations_16.txt"
WG_IFACE="wg0"
AWG_CTRL="awg-quick"

if [ ! -f "$WG_DEST" ]; then
    echo "Файл $WG_DEST не найден!"
    exit 1
fi
if [ ! -f "$WG_CONF" ]; then
    echo "Файл $WG_CONF не найден!"
    exit 2
fi

# Собираем список AllowedIPs
ALLOWED_IPS=$(grep -v '^#' "$WG_DEST" | grep -v '^$' | paste -sd, -)
if [ -z "$ALLOWED_IPS" ]; then
    echo "Список AllowedIPs пуст!"
    exit 3
fi

# Обновляем AllowedIPs в конфиге
cp "$WG_CONF" "$WG_CONF.bak.$(date +%s)"
sed -i "/^AllowedIPs[ ]*=.*/c\AllowedIPs = $ALLOWED_IPS" "$WG_CONF"
echo "AllowedIPs обновлён в $WG_CONF:"
echo "$ALLOWED_IPS"

echo "Перезапуск $WG_IFACE через $AWG_CTRL..."
$AWG_CTRL down $WG_IFACE && $AWG_CTRL up $WG_IFACE

if [ $? -eq 0 ]; then
    echo "Интерфейс $WG_IFACE успешно перезапущен."
else
    echo "Ошибка при перезапуске $WG_IFACE! Проверьте логи."
    exit 4
fi
