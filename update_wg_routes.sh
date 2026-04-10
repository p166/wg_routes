#!/bin/bash

# === ПЕРЕМЕННЫЕ ВКЛЮЧЕНИЯ ===
ENABLE_UPDATE=1                       # 1 = включить, 0 = выключить
ENABLE_APPLY=1                        # 1 = включить, 0 = выключить

# Пути и константы
INPUT=Ruantiblock.input               # единый файл: домены, IP/подсети (IPv4/IPv6)
WG_DEST=wg_destinations.txt           # IPv4‑список для WG
WG_V6=wg_v6_routes.txt                # IPv6‑подсети для маршрутов
DOMAINS=list_domains.txt              # только домены
IPS=list_ips.txt                      # IP/подсети (IPv4 + IPv6)

AUTO_DETECT_NETWORK=1                 # 1 = автоопределение интерфейсов/шлюза, 0 = только ручные значения

WG_IFACE="${WG_IFACE:-}"               # интерфейс WG (если пусто и AUTO_DETECT_NETWORK=1, будет попытка автоопределения)
ETH_IFACE="${ETH_IFACE:-}"             # LAN‑интерфейс мини‑ПК (если пусто и AUTO_DETECT_NETWORK=1, берётся из default route)
GATEWAY="${GATEWAY:-}"                 # шлюз мини‑ПК (если пусто и AUTO_DETECT_NETWORK=1, берётся из default route)
WG_V6_GATEWAY="${WG_V6_GATEWAY:-}"     # link‑local IPv6‑шлюз WG (если пусто, fe80::1%<WG_IFACE>)

FAILED_LOG=list_failed_domains.txt    # лог доменов, по которым dig не дал IP
LOGFILE=wg_update.log                 # файл для логов

MODE="$1"                             # режим: update / apply / all
# : > "$LOGFILE"
# exec >> "$LOGFILE" 2>&1

BEGIN_DATE=$(date)
echo "=== Начало работы режим $MODE: $BEGIN_DATE ==="
echo "   запуск: $0 $*"
echo "   ENABLE_UPDATE=$ENABLE_UPDATE"
echo "   ENABLE_APPLY=$ENABLE_APPLY"

detect_network_settings() {
    local default_route detected_gateway detected_eth detected_wg

    if [ "$AUTO_DETECT_NETWORK" -eq 1 ]; then
        default_route=$(ip -4 route show default 2>/dev/null | head -n 1)

        if [ -n "$default_route" ]; then
            detected_gateway=$(awk '{for (i=1; i<=NF; i++) if ($i=="via") {print $(i+1); exit}}' <<< "$default_route")
            detected_eth=$(awk '{for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}' <<< "$default_route")
        fi

        if [ -z "$ETH_IFACE" ] && [ -n "$detected_eth" ]; then
            ETH_IFACE="$detected_eth"
        fi

        if [ -z "$GATEWAY" ] && [ -n "$detected_gateway" ]; then
            GATEWAY="$detected_gateway"
        fi

        detected_wg=$(wg show interfaces 2>/dev/null | awk '{print $1; exit}')
        if [ -z "$WG_IFACE" ] && [ -n "$detected_wg" ]; then
            WG_IFACE="$detected_wg"
        fi

    fi

    [ -z "$WG_IFACE" ] && WG_IFACE="wg0"
    [ -z "$ETH_IFACE" ] && ETH_IFACE="eth0"
    [ -z "$GATEWAY" ] && GATEWAY="192.168.10.1"
    [ -z "$WG_V6_GATEWAY" ] && WG_V6_GATEWAY="fe80::1%$WG_IFACE"
}

# Нормализация IPv4 CIDR: если в записи хостовые биты, приводит к адресу сети.
normalize_ipv4_cidr() {
    local cidr="$1"
    local ip prefix o1 o2 o3 o4 ip_int mask network

    if ! [[ "$cidr" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]{1,2})$ ]]; then
        return 1
    fi

    ip="${cidr%/*}"
    prefix="${cidr#*/}"

    if (( prefix < 0 || prefix > 32 )); then
        return 1
    fi

    IFS='.' read -r o1 o2 o3 o4 <<< "$ip"
    if (( o1 > 255 || o2 > 255 || o3 > 255 || o4 > 255 )); then
        return 1
    fi

    ip_int=$(( (o1 << 24) | (o2 << 16) | (o3 << 8) | o4 ))

    if (( prefix == 0 )); then
        mask=0
    else
        mask=$(( (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF ))
    fi

    network=$(( ip_int & mask ))

    printf "%d.%d.%d.%d/%d\n" \
        $(( (network >> 24) & 255 )) \
        $(( (network >> 16) & 255 )) \
        $(( (network >> 8) & 255 )) \
        $(( network & 255 )) \
        "$prefix"
}

detect_network_settings
echo "   AUTO_DETECT_NETWORK=$AUTO_DETECT_NETWORK"
echo "   WG_IFACE=$WG_IFACE"
echo "   ETH_IFACE=$ETH_IFACE"
echo "   GATEWAY=$GATEWAY"
echo "   WG_V6_GATEWAY=$WG_V6_GATEWAY"

# === Помощь ===
if [ -z "$MODE" ]; then
    MODE=all
elif ! [[ "$MODE" =~ ^(all|update|apply)$ ]]; then
    echo "Неподдерживаемый режим: '$MODE'"
    echo "Используй:"
    echo "  $0            -> all"
    echo "  $0 update     -> обновить списки"
    echo "  $0 apply      -> применить маршруты"
    exit 1
fi




# === 1. === ОБНОВЛЕНИЕ СПИСКОВ (если ENABLE_UPDATE=1 и (MODE = all или update)) ===
if [ "$ENABLE_UPDATE" -eq 1 ] && [[ "$MODE" =~ (all|update)$ ]]; then

    echo "=== 1. Обновление списков (domains / ips / wg*) ==="

    echo "  1.1. Очистка временных файлов..."
    : > "$DOMAINS"
    : > "$IPS"
    : > "$WG_DEST"
    : > "$WG_V6"
    : > "$FAILED_LOG"
    echo "     - очищены: $DOMAINS, $IPS, $WG_DEST, $WG_V6, $FAILED_LOG"

    echo "  1.2. Разбор $INPUT..."
    while read -r line; do
        line=$(echo "$line" | xargs)
        [ -z "$line" ] && continue
        [[ "$line" =~ ^# ]] && {
            echo "     - пропускаю комментарий: $line"
            continue
        }

        if echo "$line" | grep -q '\*'; then
            echo "     - домен (с *): $line"
            echo "$line" >> "$DOMAINS"
            continue
        fi

        if echo "$line" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$'; then
            echo "     - IPv4/подсеть: $line"
            echo "$line" >> "$IPS"
        elif echo "$line" | grep -Eq '^[0-9a-fA-F:]+(/[0-9]+)?$'; then
            echo "     - IPv6/подсеть: $line"
            echo "$line" >> "$IPS"
        else
            echo "     - домен: $line"
            echo "$line" >> "$DOMAINS"
        fi
    done < "$INPUT"

    sort -u "$DOMAINS" -o "$DOMAINS"

    echo "  1.3. Сбор IPv4‑адресов для WG..."
    cat "$IPS" | grep -v ':' >> "$WG_DEST"
    cat "$IPS" | grep -E '^[0-9a-fA-F:]+/[0-9]+$' > "$WG_V6"
    count_ipv4=$(wc -l < "$WG_DEST")
    echo "     - добавлено IPv4/подсетей из файла: $count_ipv4"

    echo "     - резолв доменов в IPv4:"
    FAILED_DNS=0
    while read -r domain; do
        domain=$(echo "$domain" | xargs)
        [ -z "$domain" ] && continue

        clean_domain=$(echo "$domain" | sed 's/^\*\.//; s/^\*//')
        [ -z "$clean_domain" ] || [ "$clean_domain" = "." ] && continue

        echo "       резолв: $clean_domain"
        try_resolve=$(dig +short +time=2 +tries=1 "$clean_domain" A 2>/dev/null | \
            grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || echo "")

        if [ -z "$try_resolve" ]; then
            FAILED_DNS=$((FAILED_DNS + 1))
            echo "         резолв для '$clean_domain' не дал IP (ошибка/таймаут)"
            echo "$clean_domain" >> "$FAILED_LOG"
        else
            echo "$try_resolve" | while read -r ip; do
                echo "$ip/32" >> "$WG_DEST"
                echo "         добавлен IPv4: $ip"
            done
        fi
    done < "$DOMAINS"

    sort -u "$WG_DEST" -o "$WG_DEST"
    final_ipv4=$(wc -l < "$WG_DEST")
    echo "     - итого IPv4/подсетей после deduplication: $final_ipv4"

elif [ "$ENABLE_UPDATE" -eq 0 ] && [[ "$MODE" =~ (all|update)$ ]]; then
    echo "=== 1. ПРОПУСК обновления списков (ENABLE_UPDATE=0) ==="
else
    echo "=== 1. НЕ запускаю обновление списков (режим $MODE, ENABLE_UPDATE=$ENABLE_UPDATE) ==="
fi


# === 2. === ПРИМЕНЕНИЕ МАРШРУТОВ (если ENABLE_APPLY=1 и (MODE = all или apply)) ===
if [ "$ENABLE_APPLY" -eq 1 ] && [[ "$MODE" =~ (all|apply)$ ]]; then

    echo "=== 2. Применение маршрутов и правил ==="

    echo "  2.1. Настраиваем шлюз мини‑ПК ($GATEWAY)..."
    ip route del default 2>/dev/null || true
    ip route add default via "$GATEWAY" dev "$ETH_IFACE"

    echo "  2.2. Включаем IP‑форвардинг..."
    sysctl -w net.ipv4.ip_forward=1

    echo "  2.3. Очищаем старые iptables‑правила для wg0..."
    iptables -D FORWARD -i "$ETH_IFACE" -o "$WG_IFACE" -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i "$WG_IFACE" -o "$ETH_IFACE" -j ACCEPT 2>/dev/null || true
    iptables -t nat -D POSTROUTING -o "$WG_IFACE" -j MASQUERADE 2>/dev/null || true

    echo "  2.4. Добавляем новые правила для wg0..."
    iptables -A FORWARD -i "$ETH_IFACE" -o "$WG_IFACE" -j ACCEPT
    iptables -A FORWARD -i "$WG_IFACE" -o "$ETH_IFACE" -j ACCEPT
    iptables -t nat -A POSTROUTING -o "$WG_IFACE" -j MASQUERADE

    echo "  2.5. Обновление IPv4‑маршрутов через WG..."
    if [ ! -f "$WG_DEST" ]; then
        echo "     Файл $WG_DEST отсутствует, IPv4‑маршруты пропускаются."
    else
        while read -r net; do
            [ -z "$net" ] && continue

            normalized_net="$net"
            if [[ "$net" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]]; then
                if normalized_net=$(normalize_ipv4_cidr "$net"); then
                    if [ "$normalized_net" != "$net" ]; then
                        echo "     - нормализую IPv4 CIDR: $net -> $normalized_net"
                    fi
                else
                    echo "     - пропускаю некорректный IPv4 CIDR: $net"
                    continue
                fi
            fi

            echo "     - удаляю маршрут: $normalized_net -> dev $WG_IFACE"
            ip route delete "$normalized_net" dev "$WG_IFACE" 2>/dev/null || true
        done < "$WG_DEST"

        while read -r net; do
            [ -z "$net" ] && continue

            normalized_net="$net"
            if [[ "$net" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]]; then
                if normalized_net=$(normalize_ipv4_cidr "$net"); then
                    if [ "$normalized_net" != "$net" ]; then
                        echo "     - нормализую IPv4 CIDR: $net -> $normalized_net"
                    fi
                else
                    echo "     - пропускаю некорректный IPv4 CIDR: $net"
                    continue
                fi
            fi

            echo "     - добавляю маршрут: $normalized_net -> dev $WG_IFACE"
            ip route add "$normalized_net" dev "$WG_IFACE"
        done < "$WG_DEST"
    fi

    echo "  2.6. Обновление IPv6‑маршрутов через WG..."

    if [ ! -s "$WG_V6" ]; then
        echo "     $WG_V6 пуст или не существует, IPv6‑маршруты не добавляются."
    else
        while read -r net; do
            echo "     - удаляю IPv6: $net -> $WG_V6_GATEWAY"
            ip -6 route delete "$net" via "$WG_V6_GATEWAY" dev "$WG_IFACE" 2>/dev/null || true
        done < "$WG_V6"

        while read -r net; do
            echo "     - добавляю IPv6: $net -> $WG_V6_GATEWAY"
            ip -6 route add "$net" via "$WG_V6_GATEWAY" dev "$WG_IFACE"
        done < "$WG_V6"

        count_ipv6=$(wc -l < "$WG_V6")
    fi

else
    echo "=== 2. ПРОПУСК применения маршрутов (ENABLE_APPLY=$ENABLE_APPLY, режим $MODE) ==="
fi


# === 3. Финал ===
echo "=== Запущено: $BEGIN_DATE ==="
echo "=== Завершено: $(date) ==="
echo "=== Режим запуска: $MODE ==="
echo "=== Переменные: ENABLE_UPDATE=$ENABLE_UPDATE, ENABLE_APPLY=$ENABLE_APPLY ==="

if [ "$ENABLE_UPDATE" -eq 1 ] && [ -f "$WG_DEST" ]; then
    final_ipv4=$(wc -l < "$WG_DEST")
    echo "   IPv4/подсетей сгенерировано в WG‑файл: $final_ipv4"
else
    echo "   IPv4/подсетей в WG‑файле: $(wc -l < "$WG_DEST" 2>/dev/null || echo 0)"
fi

if [ "$ENABLE_APPLY" -eq 1 ] && [ -f "$WG_V6" ]; then
    count_ipv6=$(wc -l < "$WG_V6")
    echo "   IPv6/подсетей в WG‑файле: $count_ipv6"
else
    echo "   IPv6/подсетей в WG‑файле: $(wc -l < "$WG_V6" 2>/dev/null || echo 0)"
fi

echo "   Ошибки/пустые резолвы DNS: $FAILED_DNS"
echo "   Список проблемных доменов: $FAILED_LOG"
